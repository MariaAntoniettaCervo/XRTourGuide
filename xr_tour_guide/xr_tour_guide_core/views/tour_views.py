import base64
import re
from rest_framework.response import Response
from rest_framework import status
from ..serializers import TourSerializer, WaypointSerializer
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse, FileResponse
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
import mimetypes
from ..models import MinioStorage, Tour, Category, TypeOfImage
from rest_framework.permissions import AllowAny
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import status
from rest_framework.response import Response
import requests
import math
from django.db.models import Case, When
from ..authentication import JWTFastAPIAuthentication
import os
import dotenv
from django.http import HttpResponse
from ..services.map_extract_service import ensure_pmtiles_for_tour
from urllib.parse import quote


dotenv.load_dotenv()

def distance(x1, x2, y1, y2):
    return math.sqrt((x1 - y1)**2 + (x2 - y2)**2)

def parse_coordinates(coord_str):
    try:
        lat_str, lon_str = coord_str.split(',')
        return float(lat_str.strip()), float(lon_str.strip())
    except Exception:
        return None, None
    
@swagger_auto_schema(
    method='get',
    operation_summary="List tours by category with optional search term",
    manual_parameters=[
        openapi.Parameter(
            'searchTerm', openapi.IN_QUERY, 
            description="Keyword to search in title, description, place or coordinates", 
            type=openapi.TYPE_STRING
        ),
        openapi.Parameter(
            'category',
            openapi.IN_QUERY,
            description="Filter tours by category",
            type=openapi.TYPE_STRING
        ),
        openapi.Parameter(
            'sorted',
            openapi.IN_QUERY,
            description="Sort tours by creation time (true/false)",
            type=openapi.TYPE_STRING
        ),
        openapi.Parameter(
            'num_tours',
            openapi.IN_QUERY,
            description="Limit number of tours returned",
            type=openapi.TYPE_INTEGER
        ),
        openapi.Parameter(
            'lat',
            openapi.IN_QUERY,
            description="Latitude for distance-based sorting",
            type=openapi.TYPE_NUMBER
        ),
        openapi.Parameter(
            'lon',
            openapi.IN_QUERY,
            description="Longitude for distance-based sorting",
            type=openapi.TYPE_NUMBER
        ),
        openapi.Parameter(
            'language',
            openapi.IN_QUERY,
            description="Filter tours by language",
            type=openapi.TYPE_STRING
        )
    ],
    responses={200: TourSerializer(many=True)}
)
@api_view(['GET'])
@permission_classes([AllowAny])
def tour_list(request):
    search_term = request.GET.get('searchTerm', '')
    category = request.GET.get('category', '')
    sort_param = request.GET.get('sorted', '').lower()
    num_tours = request.GET.get('num_tours', None)
    lat = request.GET.get('lat', None)
    lon = request.GET.get('lon', None)
    language = request.GET.get('language', '').lower()

    queryset = Tour.objects.filter(parent_tours__isnull=True, is_subtour=False)

    if language:
        queryset = queryset.filter(language__iexact=language)

    if category:
        queryset = queryset.filter(category__iexact=category)

    if search_term:
        queryset = queryset.filter(
            Q(title__icontains=search_term) |
            Q(place__icontains=search_term)
        )

    if sort_param in ['true', '1', 'yes']:
        queryset = queryset.order_by('creation_time')

    if num_tours:
        try:
            limit = int(num_tours)
            if limit > 0:
                queryset = queryset[:limit]
        except (ValueError, TypeError):
            pass

    tours_list = list(queryset)

    if lat and lon:
        lat = float(lat)
        lon = float(lon)
        for tour in tours_list:
            tour_lat, tour_lon = parse_coordinates(tour.coordinates)
            if tour_lat is not None and tour_lon is not None:
                tour.distance = distance(lat, lon, tour_lat, tour_lon)
            else:
                tour.distance = float('inf')
        
        tours_list.sort(key=lambda x: x.distance)
        tours_list = tours_list[:10]

    print("Tours list: ", tours_list, flush=True)
    serializer = TourSerializer(tours_list, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method='get',
    operation_summary="Retrieve details for a specific tour",
    manual_parameters=[
        openapi.Parameter(
            'pk',
            openapi.IN_PATH,
            description="ID of the tour",
            type=openapi.TYPE_INTEGER,
            required=True
        )
    ],
    responses={
        200: TourSerializer(),
        404: openapi.Response(description="Tour not found")
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def tour_details(request, pk):
    try:
        tour = Tour.objects.get(pk=pk)
    except Tour.DoesNotExist:
        return Response({"detail": "Tour non trovato"}, status=status.HTTP_404_NOT_FOUND)
    serializer = TourSerializer(tour)
    return Response(serializer.data, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method='get',
    operation_summary="Retrieve waypoints for a specific tour including sub-tours",
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
        200: openapi.Response(
            description="Waypoints and sub-tours retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'waypoints': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                    'sub_tours': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT))
                }
            )
        ),
        404: openapi.Response(description="Tour not found")
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def tour_waypoints(request, tour_id):
    try:
        tour = Tour.objects.get(pk=tour_id)
        waypoints = tour.waypoints.order_by('position', 'id')
        sub_tour_data = None
        if tour.category == Category.MIXED:
            sub_tour = tour.sub_tours.order_by('id')
            sub_tour_data = []
            for st in sub_tour:
                st_waypoints = st.waypoints.order_by('position', 'id')
                st_serializer = WaypointSerializer(st_waypoints, many=True)
                st_data = {
                    'sub_tour': TourSerializer(st).data,
                    'waypoints': st_serializer.data
                }
                sub_tour_data.append(st_data)
    except Tour.DoesNotExist:
        return Response({"detail": "Tour non trovato"}, status=status.HTTP_404_NOT_FOUND)
    serializer = WaypointSerializer(waypoints, many=True)
    data = {
        'waypoints': serializer.data,
        'sub_tours': sub_tour_data
    }
    return Response(data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='post',
    operation_summary="Increment the view count for a specific tour",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['tour_id'],
        properties={
            'tour_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the tour'),
        },
    ),
    responses={
        200: openapi.Response(description="Tour updated successfully"),
        404: openapi.Response(description="Tour not found")
    }
)
@api_view(['POST'])
@authentication_classes([JWTFastAPIAuthentication])
@permission_classes([AllowAny])
def increment_view_count(request):
    tour_id = request.data.get('tour_id')
    try:
        tour = Tour.objects.get(id=tour_id)
    except Tour.DoesNotExist:
        return Response({"detail": "Tour not found"}, status=status.HTTP_404_NOT_FOUND)

    tour.tot_view += 1
    tour.save()

    return Response({"detail": "View count incremented successfully"}, status=status.HTTP_200_OK)

# @swagger_auto_schema(
#     method='post',
#     operation_summary="Extract and download pmtiles file for a tour based on waypoint coordinates",
#     manual_parameters=[
#         openapi.Parameter(
#             'tour_id',
#             openapi.IN_PATH,
#             description="ID of the tour",
#             type=openapi.TYPE_INTEGER,
#             required=True
#         )
#     ],
#     responses={
#         200: openapi.Response(description="Pmtiles file returned successfully"),
#         400: openapi.Response(description="Tour not found or invalid waypoints")
#     }
# )
# @api_view(['POST'])
# @authentication_classes([JWTFastAPIAuthentication])
# @permission_classes([IsAuthenticated])
# def cut_map(request, tour_id):
#     storage = MinioStorage()

#     try:
#         tour = Tour.objects.get(pk=tour_id)
#     except Tour.DoesNotExist:
#         return JsonResponse({"error": "Tour not found"}, status=400)

#     waypoints = tour.waypoints.order_by('position', 'id')
#     if not waypoints.exists():
#         return JsonResponse({"error": "No waypoints found for this tour"}, status=400)

#     lons, lats = [], []
#     for wp in waypoints:
#         try:
#             lat_str, lon_str = wp.coordinates.split(",")
#             lat, lon = float(lat_str.strip()), float(lon_str.strip())
#             lats.append(lat)
#             lons.append(lon)
#         except Exception:
#             continue

#     if not lats or not lons:
#         return JsonResponse({"error": "Waypoints have invalid coordinates"}, status=400)

#     min_lon, max_lon = min(lons), max(lons)
#     min_lat, max_lat = min(lats), max(lats)
#     print("BBOX: ", min_lon, min_lat, max_lon, max_lat, flush=True)
#     bbox = f"{min_lon - 0.1},{min_lat - 0.1},{max_lon + 0.1},{max_lat + 0.1}"
#     print("BBOX: ", bbox, flush=True)

#     payload = {
#         "tour_id": str(tour_id),
#         "bbox": bbox
#     }
#     url = os.getenv("PMTILES_URL")
#     headers = {"Content-type": "application/json"}
#     response = requests.post(url, headers=headers, json=payload)
#     if response.status_code != 200:
#         return JsonResponse({"error": "Failed to extract pmtiles"}, status=400)
    
#     file = storage.open(f"/{tour_id}/tour_{tour_id}.pmtiles", mode='rb')
#     return FileResponse(file, as_attachment=True, filename=f"tour_{tour_id}.pmtiles")

@api_view(['POST'])
@authentication_classes([JWTFastAPIAuthentication])
@permission_classes([IsAuthenticated])
def cut_map(request, tour_id):
    result = ensure_pmtiles_for_tour(tour_id)
    if not result.get("ok"):
        return JsonResponse({"error": result.get("error", "Failed to extract pmtiles")}, status=400)

    storage = MinioStorage()
    file = storage.open(result["key"], mode='rb')
    return FileResponse(file, as_attachment=True, filename=f"tour_{tour_id}.pmtiles")

@api_view(['GET'])
@authentication_classes([JWTFastAPIAuthentication])
@permission_classes([IsAuthenticated])
def download_offline_bundle(request, tour_id):
    storage = MinioStorage()
    key = f"{tour_id}/offline/offline_bundle.zip"
    if not storage.exists(key):
        return Response({"detail": "Offline bundle not ready"}, status=404)

    file = storage.open(key, mode='rb')
    response = FileResponse(file, as_attachment=True, filename=f"tour_{tour_id}_offline.zip", content_type="application/zip")
    return response

@swagger_auto_schema(
    method='get',
    operation_summary="Generate deep link page for opening tour in mobile app or web",
    manual_parameters=[
        openapi.Parameter(
            'pk',
            openapi.IN_PATH,
            description="ID of the tour",
            type=openapi.TYPE_INTEGER,
            required=True
        )
    ],
    responses={
        200: openapi.Response(description="HTML page with deep link logic")
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def tour_deep_link(request, pk):
    
    android_store = os.getenv("ANDROID_STORE")
    ios_store = os.getenv("IOS_STORE")
    
    domain = os.getenv("DOMAIN")
    domain = re.sub(r'^https?://', '', domain)
    domain_b64 = base64.b64encode(domain.encode()).decode()
    app_deep_link = f"xrtourguide://tour/{pk}?domain={domain_b64}"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Opening Tour...</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: #f5f5f5;
            }}
            .loader {{
                margin: 20px auto;
                border: 5px solid #f3f3f3;
                border-top: 5px solid #3498db;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                animation: spin 1s linear infinite;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            .message {{
                margin-top: 20px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="loader"></div>
        <div class="message" id="message">Opening tour...</div>
        
        <script>
            var appOpened = false;
            var redirected = false;
            
            function redirect() {{
                if (redirected) return;
                redirected = true;
                
                var isAndroid = /Android/i.test(navigator.userAgent);
                var isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
                var isMobile = isAndroid || isIOS;
                
                if (isMobile) {{
                    document.getElementById('message').textContent = 'App not installed. Redirecting to store...';
                    setTimeout(function() {{
                        if (isAndroid) {{
                            window.location.href = '{android_store}';
                        }} else if (isIOS) {{
                            window.location.href = '{ios_store}';
                        }}
                    }}, 500);
                }} else {{
                    document.getElementById('message').textContent = 'Redirecting to web page...';
                    setTimeout(function() {{
                        window.location.href = '/tour_details/{pk}/';
                    }}, 500);
                }}
            }}
            
            document.addEventListener('visibilitychange', function() {{
                if (document.hidden) {{
                    appOpened = true;
                }}
            }});
            
            window.addEventListener('blur', function() {{
                appOpened = true;
            }});
            
            var isAndroid = /Android/i.test(navigator.userAgent);
            var isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
            var isMobile = isAndroid || isIOS;
            
            if (isMobile) {{
                var iframe = document.createElement('iframe');
                iframe.style.display = 'none';
                iframe.src = '{app_deep_link}';
                document.body.appendChild(iframe);
                
                setTimeout(function() {{
                    if (!appOpened && !document.hidden) {{
                        redirect();
                    }}
                }}, 1500);
            }} else {{
                redirect();
            }}
        </script>
    </body>
    </html>
    """
    
    return HttpResponse(html)

@swagger_auto_schema(
    method='get',
    operation_summary="Retrieve all tours with streaming links for default images and waypoint resources",
    responses={
        200: openapi.Response(
            description="List of tours with streaming links and waypoint resources",
            examples={
                'application/json': [
                    {
                        "title": "Example Tour",
                        "subtitle": "Example Subtitle",
                        "place": "Example Place",
                        "category": "OUTDOOR",
                        "description": "Example description",
                        "user": 1,
                        "lat": 40.0,
                        "lon": 15.0,
                        "default_img": "1/default_image/example.jpg",
                        "creation_time": "2026-01-01",
                        "user_name": "username",
                        "id": 1,
                        "tot_view": 0,
                        "l_edited": "2026-01-01",
                        "rating": 0.0,
                        "rating_counter": 0,
                        "default_img_url": "http://example.com/stream_minio_resource/?tour=1&file=default_image",
                        "deep_link": "http://example.com/tour/1/",
                        "waypoints_resources": [
                            {
                                "id": 1,
                                "title": "Example Waypoint",
                                "description": "Example waypoint description",
                                "location": "40.0, 15.0",
                                "resources": {
                                    "readme": "http://example.com/stream_minio_resource/?waypoint=1&file=readme",
                                    "audio": "http://example.com/stream_minio_resource/?waypoint=1&file=audio",
                                    "pdf": "http://example.com/stream_minio_resource/?waypoint=1&file=pdf",
                                    "markdown": "http://example.com/stream_minio_resource/?waypoint=1&file=markdown",
                                    "video": "http://example.com/stream_minio_resource/?waypoint=1&file=video",
                                    "links": "http://example.com/stream_minio_resource/?waypoint=1&file=links"
                                }
                            }
                        ]
                    }
                ]
            }
        )
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def tour_informations(request):
    tours = Tour.objects.all()
    serializer = TourSerializer(tours, many=True)
    data = serializer.data
    
    domain = os.getenv("DOMAIN")
    for tour_data in data:
        tour_id = tour_data['id']
        
        coordinates = tour_data.get('coordinates', '0.0, 0.0')
        lat, lon = coordinates.split(',')
        tour_data['lat'] = float(lat.strip())
        tour_data['lon'] = float(lon.strip())
        
        tour_data.pop('coordinates', None)
        
        tour_data['default_img_url'] = f"{domain}/stream_minio_resource/?tour={tour_id}&file=default_image"
        tour_data['deep_link'] = f"{domain}/tour/{tour_id}/"
        
        tour = Tour.objects.get(id=tour_id)
        if tour.user:
            tour_data['user_name'] = tour.user.username
        
        if tour_data.get('creation_time'):
            tour_data['creation_time'] = tour_data['creation_time'].split('T')[0]
        if tour_data.get('last_edited'):
            tour_data['l_edited'] = tour_data['last_edited'].split('T')[0]
            tour_data.pop('last_edited', None)
        
        waypoints = tour.waypoints.order_by('position', 'id')
        waypoints_data = []
        
        for waypoint in waypoints:
            wp_coordinates = waypoint.coordinates or '0.0, 0.0'
            
            image_urls = [
                f"{domain}/stream_minio_resource/?waypoint={waypoint.id}&file={quote(img.image.name, safe='/')}"
                for img in waypoint.images.all()
                if img.image
            ]
            
            waypoint_info = {
                'id': waypoint.id,
                'title': waypoint.title,
                'description': waypoint.description or '',
                'location': wp_coordinates,
                'resources': {
                    'readme': f"{domain}/stream_minio_resource/?waypoint={waypoint.id}&file=readme",
                    'audio': f"{domain}/stream_minio_resource/?waypoint={waypoint.id}&file=audio",
                    'pdf': f"{domain}/stream_minio_resource/?waypoint={waypoint.id}&file=pdf",
                    'markdown': f"{domain}/stream_minio_resource/?waypoint={waypoint.id}&file=markdown",
                    'video': f"{domain}/stream_minio_resource/?waypoint={waypoint.id}&file=video",
                    'links': f"{domain}/stream_minio_resource/?waypoint={waypoint.id}&file=links",
                    'images': image_urls
                }
            }
            
            waypoints_data.append(waypoint_info)
        
        tour_data['waypoints_resources'] = waypoints_data
    
    return Response(data)

@swagger_auto_schema(
    method='post',
    operation_summary="Report a tour",
    operation_description="Increments the report count of a tour by 1. Requires authentication.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['tour_id'],
        properties={
            'tour_id': openapi.Schema(
                type=openapi.TYPE_INTEGER,
                description="ID of the tour to report"
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Tour reported successfully",
            examples={
                "application/json": {
                    "detail": "Tour reported successfully"
                }
            }
        ),
        400: openapi.Response(
            description="Missing or invalid tour_id",
            examples={
                "application/json": {
                    "detail": "tour_id is required"
                }
            }
        ),
        404: openapi.Response(
            description="Tour not found",
            examples={
                "application/json": {
                    "detail": "Tour not found"
                }
            }
        ),
        500: openapi.Response(
            description="Internal server error",
            examples={
                "application/json": {
                    "detail": "An unexpected error occurred"
                }
            }
        ),
    }
)
@api_view(['POST'])
@authentication_classes([JWTFastAPIAuthentication])
@permission_classes([IsAuthenticated])
def increment_reports(request):
    tour_id = request.data.get('tour_id')

    if tour_id is None:
        return Response({"detail": "tour_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(tour_id, int) or tour_id <= 0:
        return Response({"detail": "tour_id must be a positive integer"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tour = Tour.objects.get(id=tour_id)
    except Tour.DoesNotExist:
        return Response({"detail": "Tour not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        return Response({"detail": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    try:
        tour.reports = (tour.reports or 0) + 1
        tour.save(update_fields=['reports'])
    except Exception:
        return Response({"detail": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"detail": "Tour reported successfully"}, status=status.HTTP_200_OK)