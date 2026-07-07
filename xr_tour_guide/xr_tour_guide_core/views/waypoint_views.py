from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.http import JsonResponse, FileResponse
from rest_framework.decorators import api_view, permission_classes
import mimetypes
from ..models import MinioStorage, Waypoint, Tour, TypeOfImage
from rest_framework.permissions import AllowAny
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.response import Response
# import zlib
# from django.http import HttpResponse
import mimetypes
import os
from django.http import JsonResponse, FileResponse


def _as_bool(value):
    return str(value).lower() in {"1", "true", "yes", "on"}

def _build_storage_response(storage, file_path, attachment=False, cache_seconds=604800):
    if not file_path or not storage.exists(file_path):
        return None
    
    file_obj = storage.open(file_path, mode="rb")
    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or 'application/octet-stream'
    
    response = FileResponse(file_obj, content_type=content_type)
    response["Cache-Control"] = f"public, max-age={cache_seconds}"
    response["Content-Disposition"] = (
        f'{"attachment" if attachment else "inline"}; filename="{os.path.basename(file_path)}"'
    )
    
    return response

# @swagger_auto_schema(
#     method='get',
#     operation_summary="Stream a specific file from MinIO storage for a waypoint",
#     manual_parameters=[
#         openapi.Parameter(
#             'file', openapi.IN_QUERY, 
#             description="Exact name of the file to stream (pdf/audio/video/readme/image)", 
#             type=openapi.TYPE_STRING,
#             required=True
#         )
#     ],
#     responses={
#         200: openapi.Response(description="File streamed successfully"),
#         400: openapi.Response(description="File name not provided"),
#         404: openapi.Response(description="Waypoint or file not found")
#     }
#)
# @api_view(['GET'])
# @permission_classes([AllowAny]) 
# def stream_minio_resource(request):
#     storage = MinioStorage()
#     tour_id = request.GET.get("tour")
#     waypoint_id = request.GET.get("waypoint")
#     file_name = request.GET.get("file")
#     attachment = request.GET.get("attachment")

#     try:
#         if tour_id and waypoint_id is None:
#             tour = Tour.objects.get(id=tour_id)
#             file = storage.open(tour.default_image.name, mode='rb')
#             content_type, _ = mimetypes.guess_type(tour.default_image.name)
#             if content_type is None:
#                 content_type = 'application/octet-stream'

#             response = HttpResponse(zlib.compress(file.read()), content_type=content_type)
#             response['Content-Encoding'] = 'deflate'
#             response['Content-Disposition'] = f'{"attachment" if attachment else "inline"}; filename="{file_name}"'
#             return response
#     except Exception as e:
#         return Response({"detail": tour.default_image.name}, status=404)
    
#     if not file_name:
#         return Response({"detail": "File name non fornito"}, status=400)
        
#     try:
#         waypoint = Waypoint.objects.get(id=waypoint_id)
#     except Waypoint.DoesNotExist:
#         return Response({"detail": "Waypoint non trovato"}, status=404) 
    
#     if "pdf" == file_name:
#         file_path = waypoint.pdf_item.name
#     elif "audio" == file_name:
#         file_path = waypoint.audio_item.name
#     elif "video" == file_name:
#         file_path = waypoint.video_item.name
#     elif "readme" == file_name:
#         file_path = waypoint.readme_item.name
#     elif "img" in file_name:
#         file_path = file_name
#     else:
#         return Response({"detail": "File non trovato"}, status=404)
    
#     try:
#         if not storage.exists(file_path):
#             return Response({"detail": f"File {file_name}, {waypoint.pdf_item.name}, {file_path} non trovato"}, status=404)
#     except Exception as e:
#         return Response({"detail": "Resource not found"}, status=404)
#     file = storage.open(file_path, mode='rb')

#     content_type, _ = mimetypes.guess_type(file_path)
#     if content_type is None:
#         content_type = 'application/octet-stream'

#     response = HttpResponse(zlib.compress(file.read()), content_type=content_type)
#     response['Content-Encoding'] = 'deflate'
#     response['Content-Disposition'] = f'{"attachment" if attachment else "inline"}; filename="{file_name}"'
    
#     return response

@api_view(['GET'])
@permission_classes([AllowAny])
def stream_minio_resource(request):
    storage = MinioStorage()
    tour_id = request.GET.get("tour")
    waypoint_id = request.GET.get("waypoint")
    file_name = request.GET.get("file")
    attachment = _as_bool(request.GET.get("attachment"))

    if tour_id and waypoint_id is None:
        try:
            tour = Tour.objects.get(id=tour_id)
        except Tour.DoesNotExist:
            return Response({"detail": "Tour not found"}, status=404)
        
        response = _build_storage_response(
            storage, tour.default_image.name, attachment=attachment
        )
        
        if response is None:
            return Response({"detail": "Resource not found"}, status=404)
        return response

    if not file_name:
        return Response({"detail": "File name not provided"}, status=400)

    try:
        waypoint = Waypoint.objects.get(id=waypoint_id)
    except Waypoint.DoesNotExist:
        return Response({"detail": "Waypoint not found"}, status=404)

    file_path = None
    if file_name == "pdf":
        file_path = waypoint.pdf_item.name if waypoint.pdf_item else None
    elif file_name == "audio":
        file_path = waypoint.audio_item.name if waypoint.audio_item else None
    elif file_name == "video":
        file_path = waypoint.video_item.name if waypoint.video_item else None
    elif file_name == "readme":
        file_path = waypoint.readme_item.name if waypoint.readme_item else None
    elif "img" in file_name:
        file_path = file_name

    if not file_path:
        return Response({"detail": "File not found for the given type"}, status=404)

    response = _build_storage_response(storage, file_path, attachment=attachment)
    if response is None:
        return Response({"detail": "Resource not found"}, status=404)

    return response

@swagger_auto_schema(
    method='get',
    operation_summary="Get waypoint resources by type",
    manual_parameters=[
        openapi.Parameter(
            'waypoint_id',
            openapi.IN_QUERY,
            description="ID of the waypoint",
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'resource_type',
            openapi.IN_QUERY,
            description="Type of resource (readme/video/audio/pdf/links/images)",
            type=openapi.TYPE_STRING,
            required=True
        )
    ],
    responses={
        200: openapi.Response(
            description="Resource URLs retrieved successfully",
            examples={
                "application/json": {
                    "url": "/stream_minio_resource?waypoint=1&file=readme"
                }
            }
        ),
        400: openapi.Response(description="Invalid resource type"),
        404: openapi.Response(description="Waypoint not found")
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_waypoint_resources(request):
    waypoint_id = request.GET.get('waypoint_id')
    resource_type = request.GET.get('resource_type')

    try:
        waypoint = Waypoint.objects.get(id=waypoint_id)
    except Waypoint.DoesNotExist:
        return JsonResponse({"error": "Waypoint not found"}, status=404)

    if resource_type == "readme" and waypoint.readme_item:
        return JsonResponse({"url": f"/stream_minio_resource?waypoint={waypoint_id}&file=readme"}, status=200)
    elif resource_type == "video" and waypoint.video_item:
        return JsonResponse({"url": f"/stream_minio_resource?waypoint={waypoint_id}&file=video"}, status=200)
    elif resource_type == "audio" and waypoint.audio_item:
        return JsonResponse({"url": f"/stream_minio_resource?waypoint={waypoint_id}&file=audio"}, status=200)
    elif resource_type == "pdf" and waypoint.pdf_item:
        return JsonResponse({"url": f"/stream_minio_resource?waypoint={waypoint_id}&file=pdf"}, status=200)
    elif resource_type == "links" and waypoint.links.exists():
        links = waypoint.links.all()
        links = [link.link for link in links]
        return JsonResponse({"links": links}, status=200)
    elif resource_type == "images":
        images = waypoint.images.filter(type_of_images=TypeOfImage.ADDITIONAL_IMAGES)
        if not images.exists():
            images = waypoint.images.filter(type_of_images=TypeOfImage.DEFAULT)[:2]
        images = [f"/stream_minio_resource/?waypoint={waypoint_id}&file={img.image.name}" for img in images]
        return JsonResponse({"images": images}, status=200)

    else:
        return JsonResponse({"error": "Invalid resource type"}, status=400)