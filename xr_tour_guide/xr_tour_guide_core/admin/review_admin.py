from ..models import Review
from django.contrib import admin
from unfold.admin import ModelAdmin
from django.db.models import Q
from django.urls import path
from django.utils.translation import gettext_lazy as _

class ReviewAdmin(ModelAdmin):
    list_display = ("tour", "user", "timestamp")
    readonly_fields = ("user", "timestamp", "rating", "comment", "tour")
    search_fields = ('comment', )
    model = Review
    show_add_button = False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(Q(user=request.user) | Q(tour__user=request.user))
        return qs
    
    def get_urls(self):
        urls = super().get_urls()
        return [u for u in urls if "add" not in u.pattern.regex.pattern]
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.tour.status in ['SERVING', 'BUILDING', 'ENQUEUED']:
            return False
        if not request.user.is_superuser and obj.user != request.user:
            return False
        return True
    
    def has_add_permission(self, request, obj=None):
        return False

admin.site.register(Review, ReviewAdmin)