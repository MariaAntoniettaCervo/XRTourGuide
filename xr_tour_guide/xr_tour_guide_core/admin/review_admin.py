from ..models import Review, Tour
from django.contrib import admin, messages
from unfold.admin import ModelAdmin
from django.db.models import Q, Count, Avg, Max
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.http import Http404
from .permission import visible_tours_queryset


class ReviewAdmin(ModelAdmin):
    change_list_template = "admin/xr_tour_guide_core/review/change_list.html"

    list_display = ("tour", "user", "rating", "timestamp")
    readonly_fields = ("user", "timestamp", "rating", "comment", "tour")
    search_fields = ("comment", "tour__title", "user__username", "user__email")
    model = Review
    show_add_button = False

    # def get_queryset(self, request):
    #     qs = super().get_queryset(request)

    #     if not request.user.is_superuser:
    #         qs = qs.filter(Q(user=request.user) | Q(tour__user=request.user))

    #     return qs

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        visible_tours = visible_tours_queryset(request.user, Tour.objects.all())

        return qs.filter(
            Q(user=request.user) | Q(tour__in=visible_tours)
        )


    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "tour/<int:tour_id>/",
                self.admin_site.admin_view(self.tour_reviews_view),
                name="xr_tour_guide_core_review_tour_reviews",
            ),
        ]

        urls = [u for u in urls if "add" not in u.pattern.regex.pattern]

        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        reviews_qs = self.get_queryset(request)

        tour_ids = reviews_qs.values_list("tour_id", flat=True).distinct()

        tours = (
            Tour.objects
            .filter(id__in=tour_ids)
            .annotate(
                review_count=Count("reviews", distinct=True),
                avg_rating=Avg("reviews__rating"),
                latest_review=Max("reviews__timestamp"),
            )
            .order_by("-latest_review", "title")
        )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Reviews by Tour"),
            "tours": tours,
            "total_tours": tours.count(),
        }

        if extra_context:
            context.update(extra_context)

        return TemplateResponse(
            request,
            self.change_list_template,
            context,
        )

    def tour_reviews_view(self, request, tour_id):
        reviews_qs = self.get_queryset(request)

        tour = get_object_or_404(Tour, pk=tour_id)

        if not reviews_qs.filter(tour=tour).exists():
            raise Http404()

        reviews = (
            reviews_qs
            .filter(tour=tour)
            .select_related("user", "tour")
            .order_by("-timestamp")
        )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Reviews for %(tour)s") % {"tour": tour.title},
            "tour": tour,
            "reviews": reviews,
            "review_count": reviews.count(),
            "avg_rating": reviews.aggregate(avg=Avg("rating"))["avg"],
        }

        return TemplateResponse(
            request,
            "admin/xr_tour_guide_core/review/tour_reviews.html",
            context,
        )

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)

        if not has_permission:
            return False

        if obj is None:
            return True

        if obj.tour.status in ["SERVING", "BUILDING", "ENQUEUED"]:
            return False

        if not request.user.is_superuser and obj.user != request.user:
            return False

        return True

    def has_add_permission(self, request, obj=None):
        return False


admin.site.register(Review, ReviewAdmin)
