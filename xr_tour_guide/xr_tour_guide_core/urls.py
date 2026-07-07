from django.urls import path, re_path
from .views.ai_views import *
# from .views.user_views import *
from .views.tour_views import *
from .views.waypoint_views import *
from .views.review_views import *
from .views.control_views import *
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
   openapi.Info(
      title="XRTourGuide API",
      default_version='v1',
      description="These are the API endpoints for XRTourGuide.",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="isislab.unisa@gmail.com"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path("tour_list/", tour_list, name="tour_list"),
    path("tour_details/<int:pk>/", tour_details, name="tour_details"),
    path("stream_minio_resource/", stream_minio_resource, name="stream_minio_resource"),
    path(
        "get_reviews_by_tour_id/<int:tour_id>/",
        get_reviews_by_tour_id,
        name="get_reviews_by_tour_id",
    ),
    re_path(r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name='schema-json'
    ),
    re_path(r"^swagger/$",
        schema_view.with_ui('swagger', cache_timeout=0),
        name='schema-swagger-ui'
    ),
    re_path(r"^docs/$",
        schema_view.with_ui('redoc', cache_timeout=0),
        name='schema-redoc'
    ),
    path("tour_waypoints/<int:tour_id>/", tour_waypoints, name="tour_waypoints"),
    path("create_review/", create_review, name="create_review"),
    path("get_reviews_by_user/", get_reviews_by_user, name="get_reviews_by_user"),
    path("increment_view_count/", increment_view_count, name="increment_view_count"),
    path("build/", build, name="build"),
    path("complete_build/", complete_build, name="complete_build"),
    path("load_model/<int:tour_id>/", load_model, name="load_model"),
    path("inference/", inference, name="inference"),
    path("get_waypoint_resources/", get_waypoint_resources, name="get_waypoint_resources"),
    path("download_model/", download_model, name="download_model"),
    path("cut_map/<int:tour_id>/", cut_map, name="cut_map"),
    path("health_check/", health_check, name="health_check"),
    path("tour/<int:pk>/", tour_deep_link, name="tour_deep_link"),
    path("tour-informations/", tour_informations, name="tour_informations"),
    path('increment-reports/', increment_reports, name="increment_reports"),
    path('has_reviewed_tour/<int:tour_id>/', has_reviewed_tour, name="has_reviewed_tour"),
    path("download_offline_bundle/<int:tour_id>/", download_offline_bundle, name="download_offline_bundle"),
]