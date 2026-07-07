from .base import UnfoldNestedStackedInline, UnfoldNestedTabularInline
from django.contrib import admin
from .user_admin import CustomUserAdmin
from .waypoint_admin import WaypointAdmin, WaypointViewImageAdmin
from .tour_admin import TourAdmin
from .review_admin import ReviewAdmin

__all__ = [
    'UnfoldNestedStackedInline',
    'UnfoldNestedTabularInline',
    'CustomUserAdmin',
    'ReviewAdmin',
    'WaypointViewImageAdmin',
    'TourAdmin',
]

admin.site.site_header = "🗺️ Tour Management System"
admin.site.site_title = "XRTourGuide"
admin.site.index_title = "Benvenuto nel pannello di gestione tour"