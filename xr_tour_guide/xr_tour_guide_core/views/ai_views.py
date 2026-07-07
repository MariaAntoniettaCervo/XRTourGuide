import os
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse, JsonResponse, FileResponse
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from ..models import MinioStorage, Tour
from rest_framework.permissions import AllowAny
from django.core.mail import send_mail
from django.shortcuts import redirect
from xr_tour_guide.tasks import call_api_and_save
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
import requests
import redis
from django.conf import settings
from ..authentication import JWTFastAPIAuthentication
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from xr_tour_guide.tasks import generate_offline_bundle


redis_client = redis.StrictRedis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

@login_required
@require_http_methods(['POST'])
def build(request):
    tour_id = int(request.POST.get('tour_id'))
    try:
        tour = Tour.objects.get(pk=tour_id)
    except Tour.DoesNotExist as e:
        print(f"This tour: {tour_id} does not exist")
    
    if tour.user != request.user:
        return JsonResponse({"message": "You are not authorized to build this tour"}, status=403)
    
    if tour.status == "READY":
        tour.status = "ENQUEUED"
        tour.save()
        
        if tour.category == "GUIDE":
            generate_offline_bundle.delay(tour.id)
        else:
            call_api_and_save.apply_async(args=[tour.id], queue='api_tasks')
    else:
        return JsonResponse({"message": "Tour already built"}, status=400)
    return redirect(settings.LOGIN_REDIRECT_URL)

@swagger_auto_schema(
    method='post',
    operation_summary="Complete the build process for a tour",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['poi_name', 'poi_id', 'index_url', 'status'],
        properties={
            'poi_name': openapi.Schema(type=openapi.TYPE_STRING, description='Name of the POI/tour'),
            'poi_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the POI/tour'),
            'index_url': openapi.Schema(type=openapi.TYPE_STRING, description='URL of the JSON index'),
            'model_url': openapi.Schema(type=openapi.TYPE_STRING, description='Legacy URL of the PyTorch model', nullable=True),
            'status': openapi.Schema(type=openapi.TYPE_STRING, description='Build status (COMPLETED or FAILED)'),
        }
    ),
    responses={
        200: openapi.Response(description="Build completed successfully"),
        404: openapi.Response(description="Tour not found"),
        500: openapi.Response(description="Error saving tour")
    }
)
@api_view(['POST'])
# @authentication_classes([JWTFastAPIAuthentication])
@permission_classes([AllowAny])
def complete_build(request):
    storage = MinioStorage()
    tour_title = request.data.get('poi_name')
    tour_id = request.data.get('poi_id')
    index_url = request.data.get('index_url')
    model_url = request.data.get('model_url')
    status = request.data.get('status')

    redis_client = redis.StrictRedis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

    if status == "COMPLETED":
        try:
            tour = Tour.objects.get(pk=int(tour_id))
            tour.model_path = index_url
            tour.status = "BUILT"
            tour.save()
            generate_offline_bundle.delay(tour.id)
        except Tour.DoesNotExist:
            return JsonResponse({"error": "POI not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": f"Error saving POI: {str(e)}"}, status=500)

        try:
            if tour.user and tour.user.email:
                send_mail(
                    'Build completata',
                    f"Lezione {tour.title} buildata.",
                    os.environ.get('EMAIL_HOST_USER'),
                    [tour.user.email],
                    fail_silently=True,
                )
        except Exception as e:
            print(f"Errore nell'invio dell'email: {e}")

        try:
            redis_client.delete("build_lock")
        except Exception as e:
            print(f"Errore nell'eliminazione del lock: {e}")

        try:
            prefix = f"{tour_id}/data/"
            bucket = storage.bucket
            objects_to_delete = bucket.objects.filter(Prefix=prefix)
            for obj in objects_to_delete:
                obj.delete()
                        
        except Exception as e:
            print(f"Errore nell'eliminazione degli oggetti: {e}", flush=True)

        return JsonResponse({"message": "Build completata"}, status=200)
    else:
        tour = Tour.objects.get(pk=tour_id)
        tour.status = "FAILED"
        tour.save()

        try:
            if tour.user and tour.user.email:
                send_mail(
                    'Build fallita',
                    f"Build Fallita {tour.title}.",
                    os.environ.get('EMAIL_HOST_USER'),
                    [tour.user.email],
                    fail_silently=True,
                )
        except Exception as e:
            print(f"Errore nell'invio dell'email: {e}")

        try:
            redis_client.delete("build_lock")
        except Exception as e:
            print(f"Errore nell'eliminazione del lock: {e}")

        return JsonResponse({"error": "POI not found"}, status=404)

@swagger_auto_schema(
    method='get',
    operation_summary="Load model for a specific tour",
    manual_parameters=[
        openapi.Parameter(
            'tour_id',
            openapi.IN_PATH,
            description="ID of the tour",
            type=openapi.TYPE_INTEGER,
            required=True
        )
    ],
    responses={
        200: openapi.Response(description="Model loaded successfully"),
        404: openapi.Response(description="Tour or model not found")
    }
)
@api_view(["GET"])
@authentication_classes([JWTFastAPIAuthentication])
@permission_classes([IsAuthenticated])
def load_model(request, tour_id):
    try:
        tour = Tour.objects.get(pk=tour_id)
    except Tour.DoesNotExist:
        return JsonResponse({"error": "POI not found"}, status=404)
    storage = MinioStorage()
    if storage.exists(
        f"{tour_id}/training_data.json"
    ):
        model_file = storage.open(f"/{tour_id}/training_data.json")
        os.makedirs("models", exist_ok=True)
        with open(f"models/training_data_{tour_id}.json", "wb") as f:
            for chunk in model_file.chunks():
                f.write(chunk)
    else:
        return JsonResponse({"error": "Model not found"}, status=404)
    return JsonResponse({"message": "Model loaded"}, status=200)

@swagger_auto_schema(
    method='post',
    operation_summary="Run inference on an image for a specific tour",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['tour_id', 'img'],
        properties={
            'tour_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the tour'),
            'img': openapi.Schema(type=openapi.TYPE_STRING, description='Image data for inference'),
        },
    ),
    responses={
        200: openapi.Response(
            description="Inference completed",
            examples={
                "application/json": {
                    "result": 1,
                    "available_resources": {
                        "pdf": 1,
                        "readme": 0,
                        "video": 1,
                        "audio": 0,
                        "links": 1
                    }
                }
            }
        ),
        404: openapi.Response(description="Tour not found")
    }
)
@api_view(['POST'])
@authentication_classes([JWTFastAPIAuthentication])
@permission_classes([IsAuthenticated])
def inference(request):
    tour_id = request.data.get('tour_id')
    try:
        tour = Tour.objects.get(pk=tour_id)
    except Tour.DoesNotExist:
        return JsonResponse({"error": "POI not found"}, status=404)

    # payload = {
    #     "poi_id": str(tour_id),
    #     "poi_name": tour.title,
    #     "inference_image": request.data.get('img'),
    #     "model_url": f"{tour.pk}/training_data.json",
    #     "index_url": f"{tour.pk}/training_data.json",
    #     "gps_lat": request.data.get('gps_lat'),
    #     "gps_lon": request.data.get('gps_lon'),
    #     "gps_accuracy_m": request.data.get('gps_accuracy_m'),
    # }
    # url = os.getenv("INFERENCE_ENDPOINT")
    # headers = {"Content-type": "application/json"}
    # response = requests.post(url, headers=headers, json=payload)
    
    payload = {
        "poi_id": str(tour_id),
        "poi_name": tour.title,
        "model_url": f"{tour.pk}/training_data.json",
        "index_url": f"{tour.pk}/training_data.json",
        "gps_lat": request.data.get("gps_lat"),
        "gps_lon": request.data.get("gps_lon"),
        "gps_accuracy_m": request.data.get("gps_accuracy_m"),
    }

    url = os.getenv("INFERENCE_ENDPOINT")

    uploaded_file = request.FILES.get("img") or request.FILES.get("image")

    if uploaded_file is not None:
        files = {
            "image": (
                uploaded_file.name or "query.jpg",
                uploaded_file.read(),
                uploaded_file.content_type or "image/jpeg",
            )
        }

        response = requests.post(
            url,
            data=payload,
            files=files,
            timeout=60,
        )
    else:
        payload["inference_image"] = request.data.get("img")

        response = requests.post(
            url,
            headers={"Content-type": "application/json"},
            json=payload,
            timeout=60,
        )

    result = response.json()
    print(f"RESPONSE: {result.get('message')}", flush=True)

    print("INFERENCE DONE", flush=True)
    
    
    if result is None:
        response_data = {
            "result": -1,
            "available_resources": {
                "pdf": 0,
                "readme": 0,
                "video": 0,
                "audio": 0,
                "links": 0,
            }
        }
        return JsonResponse(response_data, status=200)
    
    waypoint = tour.waypoints.filter(title=result.get("message"), is_preliminary_info=False).first()

    
    if waypoint is None:
        for sub_tour in tour.sub_tours.all():
            waypoint = sub_tour.waypoints.filter(title=result.get("message"), is_preliminary_info=False).first()
            if waypoint:
                break

    if waypoint is None:
        print("Waypoint non trovato", flush=True)
        return JsonResponse({
            "result": -1,
            "message": "Waypoint not found in waypoints or in sub-tours",
            "available_resources": {
                "pdf": 0,
                "readme": 0,
                "video": 0,
                "audio": 0,
                "links": 0,
            }
        }, status=200)

    available_resources = {
        "pdf": int(bool(waypoint.pdf_item and waypoint.pdf_item.name)),
        "readme": int(bool(waypoint.readme_item and waypoint.readme_item.name)),
        "video": int(bool(waypoint.video_item and waypoint.video_item.name)),
        "audio": int(bool(waypoint.audio_item and waypoint.audio_item.name)),
        "links": int(waypoint.links.exists())
    }

    return JsonResponse({
        "result": waypoint.id,
        "available_resources": available_resources
    }, status=200)

@swagger_auto_schema(
    method='get',
    operation_summary="Download training data model for a tour",
    manual_parameters=[
        openapi.Parameter(
            'tour_id',
            openapi.IN_QUERY,
            description="ID of the tour",
            type=openapi.TYPE_STRING,
            required=True
        )
    ],
    responses={
        200: openapi.Response(
            description="Training data retrieved successfully",
            content_type='application/json'
        )
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def download_model(request):
    storage = MinioStorage()
    tour_id = request.GET.get('tour_id')
    try:
        with storage.open(f"{tour_id}/training_data.json", mode='rb') as f:
            model = f.read().decode()
    except Exception as e:
        print(f"Errore nell'apertura del file: {e}")
    return HttpResponse(model, content_type='application/json')