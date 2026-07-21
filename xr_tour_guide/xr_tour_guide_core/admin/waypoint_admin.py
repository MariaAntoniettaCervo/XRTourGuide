from django.contrib import admin
from django import forms
from location_field.widgets import LocationWidget
from location_field.models.plain import PlainLocationField
import nested_admin
from unfold.admin import ModelAdmin
from ..models import Tour, Waypoint, WaypointViewImage, WaypointViewLink, TypeOfImage
from django.forms.widgets import ClearableFileInput
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.db import models
from django.urls import reverse
from ..forms.waypoint_form import WaypointForm
from .base import UnfoldNestedStackedInline
from django.utils.translation import gettext_lazy as _
from .permission import can_edit_tour, can_view_tour, visible_tours_queryset

class ReadonlyWaypointInline(UnfoldNestedStackedInline):
    model = Waypoint
    extra = 0
    can_delete = False
    show_change_link = False

    readonly_fields = (
        "position",
        "title",
        "description",
        "is_preliminary_info",
        "place",
        "coordinates",
        "readonly_default_images",
        "readonly_additional_images",
        "readonly_resources",
        "readonly_links",
    )

    fieldsets = (
        (_("📍 Basic Information"), {
            "fields": (
                "position",
                "title",
                "description",
                "is_preliminary_info",
                "place",
                "coordinates",
            ),
        }),
        (_("🖼️ Images"), {
            "fields": (
                "readonly_default_images",
                "readonly_additional_images",
            ),
            "classes": ("collapse",),
        }),
        (_("🎬 Multimedia Resources"), {
            "fields": (
                "readonly_resources",
                "readonly_links",
            ),
            "classes": ("collapse",),
        }),
    )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_view_tour(request.user, obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("🖼️ Main Images"))
    def readonly_default_images(self, obj):
        return self._render_images(obj, TypeOfImage.DEFAULT)

    @admin.display(description=_("🖼️ Additional Images"))
    def readonly_additional_images(self, obj):
        return self._render_images(obj, TypeOfImage.ADDITIONAL_IMAGES)

    def _render_images(self, obj, image_type):
        if not obj or not obj.pk:
            return "-"

        images = WaypointViewImage.objects.filter(
            waypoint=obj,
            type_of_images=image_type,
        )

        if not images.exists():
            return mark_safe(
                '<div style="color: light-dark(#6b7280, #9ca3af);">'
                f'{_("No images uploaded.")}'
                '</div>'
            )

        html = [
            '<div style="display:flex; flex-wrap:wrap; gap:16px;">'
        ]

        for image in images:
            img_url = (
                f"/stream_minio_resource/"
                f"?tour={obj.tour.pk}"
                f"&waypoint={obj.pk}"
                f"&file={image.image.name}"
            )

            html.append(f"""
                <div style="
                    width: 180px;
                    border: 1px solid light-dark(#e5e7eb, #374151);
                    border-radius: 8px;
                    overflow: hidden;
                    background: light-dark(#ffffff, #1f2937);
                ">
                    <img src="{img_url}"
                         alt="Waypoint image"
                         onclick="window.open('{img_url}', '_blank')"
                         style="
                            width: 100%;
                            height: 130px;
                            object-fit: cover;
                            cursor: pointer;
                            background: light-dark(#f3f4f6, #111827);
                         "
                         loading="lazy"
                         decoding="async" />
                    <div style="
                        padding: 8px;
                        font-size: 12px;
                        color: light-dark(#6b7280, #9ca3af);
                        word-break: break-all;
                    ">
                        {image.image.name.split("/")[-1]}
                    </div>
                </div>
            """)

        html.append("</div>")
        return mark_safe("".join(html))

    @admin.display(description=_("🎬 Uploaded Resources"))
    def readonly_resources(self, obj):
        if not obj or not obj.pk:
            return "-"

        resources = [
            ("📄 PDF", obj.pdf_item),
            ("🎧 Audio", obj.audio_item),
            ("🎥 Video", obj.video_item),
            ("📝 Readme", obj.readme_item),
        ]

        rows = []

        for label, file_field in resources:
            if not file_field:
                continue

            resource_url = (
                f"/stream_minio_resource/"
                f"?tour={obj.tour.pk}"
                f"&waypoint={obj.pk}"
                f"&file={file_field.name}"
            )

            rows.append(f"""
                <div style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 12px;
                    padding: 10px 12px;
                    border: 1px solid light-dark(#e5e7eb, #374151);
                    border-radius: 8px;
                    background: light-dark(#ffffff, #1f2937);
                    margin-bottom: 8px;
                ">
                    <div>
                        <strong>{label}</strong>
                        <div style="
                            font-size: 12px;
                            color: light-dark(#6b7280, #9ca3af);
                            word-break: break-all;
                        ">
                            {file_field.name}
                        </div>
                    </div>
                    <a href="{resource_url}"
                       target="_blank"
                       style="
                            color: light-dark(#2563eb, #60a5fa);
                            font-weight: 600;
                            text-decoration: none;
                       ">
                        {_("Open")}
                    </a>
                </div>
            """)

        if not rows:
            return mark_safe(
                '<div style="color: light-dark(#6b7280, #9ca3af);">'
                f'{_("No resources uploaded.")}'
                '</div>'
            )

        return mark_safe("".join(rows))

    @admin.display(description=_("🔗 Links"))
    def readonly_links(self, obj):
        if not obj or not obj.pk:
            return "-"

        links = WaypointViewLink.objects.filter(waypoint=obj)

        if not links.exists():
            return mark_safe(
                '<div style="color: light-dark(#6b7280, #9ca3af);">'
                f'{_("No links uploaded.")}'
                '</div>'
            )

        html = ['<ul style="margin:0; padding-left:18px;">']

        for link in links:
            if not link.link:
                continue

            html.append(f"""
                <li style="margin-bottom: 6px;">
                    <a href="{link.link}"
                       target="_blank"
                       style="
                            color: light-dark(#2563eb, #60a5fa);
                            font-weight: 600;
                            text-decoration: none;
                            word-break: break-all;
                       ">
                        {link.link}
                    </a>
                </li>
            """)

        html.append("</ul>")
        return mark_safe("".join(html))


class WaypointAdmin(UnfoldNestedStackedInline):
    model = Waypoint
    form = WaypointForm
    extra = 0
    collapsible = True
    
    sortable_field_name = 'position'
    ordering_field = 'position'
    hide_ordering_field = True
    
    verbose_name = _("Point of Interest")
    verbose_name_plural = _("Tour Points of Interest")
    readonly_fields = ['display_existing_images', 'display_existing_additional_images']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)

        visible_tours = visible_tours_queryset(
            request.user,
            Tour.objects.all(),
        )
        
        return qs.filter(tour__in=visible_tours).distinct()
    
    fieldsets = (
        (_('📍 Basic Information'), {
            'fields': ('position', 'title', 'description'),
            'description': (
                '<div style="background: light-dark(#dbeafe, #1e3a8a); padding: 12px; border-radius: 6px; '
                'margin-bottom: 12px; border-left: 4px solid light-dark(#3b82f6, #60a5fa); '
                'color: light-dark(#1e3a8a, #dbeafe);">'
                '<strong>💡 ' + str(_('Tip:')) + '</strong> ' +
                str(_('Start with a clear title and a brief description. You\'ll add details later.')) +
                '</div>'
            )
        }),
        (_('ℹ️ Preliminary Information'), {
            'fields': ('is_preliminary_info',),
            'description': (
                '<div style="background: light-dark(#eef2ff, #312e81); padding: 12px; border-radius: 6px; '
                'margin-bottom: 12px; border-left: 4px solid light-dark(#6366f1, #a5b4fc); '
                'color: light-dark(#312e81, #eef2ff);">'
                '<strong>ℹ️ ' + str(_('What is this?')) + '</strong><br>' +
                str(_('Enable this option when the point of interest is not a real geolocated stop, but an introductory or informational section shown at the beginning of the tour.')) +
                '<br><br>'
                '<strong>' + str(_('Effects:')) + '</strong>'
                '<ul style="margin: 8px 0 0 18px; padding: 0;">'
                '<li>' + str(_('It is shown in the itinerary and mobile app as preliminary information.')) + '</li>'
                '<li>' + str(_('It is excluded from the map and geolocation-based navigation.')) + '</li>'
                '<li>' + str(_('It is excluded from AI recognition and model training.')) + '</li>'
                '<li>' + str(_('It is excluded from tour completion logic.')) + '</li>'
                '</ul>'
                '</div>'
            ),
        }),
        (_('🗺️ Map Location'), {
            'fields': ('place', 'coordinates',),
            'description': (
                '<div style="background: light-dark(#fef3c7, #78350f); padding: 12px; border-radius: 6px; '
                'margin-bottom: 12px; border-left: 4px solid light-dark(#f59e0b, #fbbf24); '
                'color: light-dark(#78350f, #fef3c7);">'
                '<strong>📌 ' + str(_('How to select:')) + '</strong> ' +
                str(_('Click on the map at the exact point where the location is. You can drag the marker to adjust its position.')) +
                '</div>'
            )
        }),
        (_('🖼️ Images'), {
            'fields': ('uploaded_images', 'display_existing_images'),
            'classes': ('collapse',),
            'description': (
                '<div style="background: light-dark(#d1fae5, #065f46); padding: 12px; border-radius: 6px; '
                'margin-bottom: 12px; border-left: 4px solid light-dark(#10b981, #34d399); '
                'color: light-dark(#065f46, #d1fae5);">'
                '<strong>📷 ' + str(_('Advice:')) + '</strong> ' +
                str(_('Upload 3-5 good quality images showing the location from different angles. Photos help visitors recognize the place!')) +
                '</div>'
            )
        }),
        (_('🎬 Multimedia Content (Optional)'), {
            'fields': ('pdf_item', 'video_item', 'audio_item', 'readme_text', 'additional_images', 'display_existing_additional_images', 'links'),
            'classes': ('collapse',),
            'description': (
                '<div style="background: light-dark(#e0e7ff, #3730a3); padding: 12px; border-radius: 6px; '
                'margin-bottom: 12px; border-left: 4px solid light-dark(#6366f1, #818cf8); '
                'color: light-dark(#3730a3, #e0e7ff);">'
                '<strong>🎥 ' + str(_('Optional but recommended:')) + '</strong> ' +
                str(_('Add extra content to enrich the experience. A PDF with historical info, a video, or an audio guide make the tour more complete.')) +
                '</div>'
            )
        }),
    )
    
    @admin.display(description=_("🖼️ Image Gallery"))
    def display_existing_images(self, obj):
        if not obj or not obj.pk:
            return mark_safe(
                '<div style="background: light-dark(#fef3c7, #78350f); padding: 12px; border-radius: 6px; '
                'border-left: 4px solid light-dark(#f59e0b, #fbbf24); color: light-dark(#78350f, #fef3c7);">'
                '<p style="margin: 0; font-size: 0.875rem;">⚠️ ' + str(_('Save the point of interest first to upload images')) + '</p>'
                '</div>'
            )
        
        images = WaypointViewImage.objects.filter(waypoint=obj, type_of_images=TypeOfImage.DEFAULT)
        
        if not images.exists():
            return mark_safe(
                '<div style="background: light-dark(#f3f4f6, #1f2937); padding: 12px; border-radius: 6px; '
                'color: light-dark(#6b7280, #9ca3af);">'
                '<p style="margin: 0; font-size: 0.875rem;">📷 ' + str(_('No images uploaded yet')) + '</p>'
                '</div>'
            )
        
        # html_parts = [
        #     '<div style="background: light-dark(#ffffff, #1f2937); padding: 16px; border-radius: 8px; '
        #     'border: 1px solid light-dark(#e5e7eb, #374151);">',
        #     f'<p style="margin: 0 0 12px 0; font-weight: 600; color: light-dark(#374151, #e5e7eb);">📷 {images.count()} ' + str(_('images uploaded')) + '</p>',
        #     '<div style="display: flex; flex-wrap: wrap; gap: 16px;">'
        # ]
        
        html_parts = [
            '<div data-waypoint-gallery="1" style="background: light-dark(#ffffff, #1f2937); padding: 16px; border-radius: 8px; '
            'border: 1px solid light-dark(#e5e7eb, #374151);">',
            f'<p style="margin: 0 0 12px 0; font-weight: 600; color: light-dark(#374151, #e5e7eb);">📷 {images.count()} ' + str(_('images uploaded')) + '</p>',
            '<div style="display: flex; flex-wrap: wrap; gap: 16px;">'
        ]
        
        for img in images:
            app_label = WaypointViewImage._meta.app_label
            model_name = WaypointViewImage._meta.model_name
            
            try:
                change_url = reverse(f'admin:{app_label}_{model_name}_change', args=[img.pk])
                delete_link = (
                    f'<a href="{change_url}" '
                    f'style="color: light-dark(#dc2626, #f87171); font-size: 0.75rem; font-weight: 500; text-decoration: none;" '
                    f'target="_blank">🗑️ {_("Manage")}</a>'
                )
            except:
                delete_link = ''
            
            img_url = f"/stream_minio_resource/?tour={img.waypoint.tour.pk}&waypoint={img.waypoint.pk}&file={img.image.name}"
            
            # html_parts.append(f'''
            #     <div style="width: 200px; border: 1px solid light-dark(#e5e7eb, #374151); border-radius: 8px; 
            #          overflow: hidden; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);">
            #         <img src="{img_url}" 
            #              alt="View image" 
            #              onclick="window.open('{img_url}', '_blank')"
            #              style="width: 100%; height: 160px; object-fit: cover; cursor: pointer;"
            #              title="{_('Click to view image in full screen')}"
            #         />
            #         <div style="padding: 8px; background: light-dark(#ffffff, #1f2937); display: flex; 
            #              justify-content: space-between; align-items: center;">
            #             <span style="font-size: 0.75rem; color: light-dark(#6b7280, #9ca3af);">ID: {img.pk}</span>
            #             {delete_link}
            #         </div>
            #     </div>
            # ''')
            
            html_parts.append(f'''
                <div style="width: 200px; border: 1px solid light-dark(#e5e7eb, #374151); border-radius: 8px; 
                     overflow: hidden; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);">
                <img src="data:image/gif;base64,R0lGODlhAQABAAAAACwAAAAAAQABAAA="
                    data-waypoint-lazy-src="{img_url}"
                    alt="View image"
                    onclick="window.open('{img_url}', '_blank')"
                    style="width: 100%; height: 160px; object-fit: cover; cursor: pointer; background: light-dark(#f3f4f6, #111827);"
                    title="{_('Click to view image in full screen')}"
                    loading="lazy"
                    decoding="async"
                />
                <div style="padding: 8px; background: light-dark(#ffffff, #1f2937); display: flex; 
                         justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.75rem; color: light-dark(#6b7280, #9ca3af);">ID: {img.pk}</span>
                        {delete_link}
                    </div>
                </div>
            ''')

        
        html_parts.append('</div></div>')
        
        return mark_safe(''.join(html_parts))
    
    @admin.display(description=_("🖼️ Additional Image Gallery"))
    def display_existing_additional_images(self, obj):
        if not obj or not obj.pk:
            return mark_safe(
                '<div style="background: light-dark(#fef3c7, #78350f); padding: 12px; border-radius: 6px; '
                'border-left: 4px solid light-dark(#f59e0b, #fbbf24); color: light-dark(#78350f, #fef3c7);">'
                '<p style="margin: 0; font-size: 0.875rem;">⚠️ ' + str(_('Save the point of interest first to upload additional images')) + '</p>'
                '</div>'
            )

        images = WaypointViewImage.objects.filter(
            waypoint=obj,
            type_of_images=TypeOfImage.ADDITIONAL_IMAGES
        )

        if not images.exists():
            return mark_safe(
                '<div style="background: light-dark(#f3f4f6, #1f2937); padding: 12px; border-radius: 6px; '
                'color: light-dark(#6b7280, #9ca3af);">'
                '<p style="margin: 0; font-size: 0.875rem;">🖼️ ' + str(_('No additional images uploaded yet')) + '</p>'
                '</div>'
            )

        html_parts = [
            '<div data-waypoint-gallery="1" style="background: light-dark(#ffffff, #1f2937); padding: 16px; border-radius: 8px; '
            'border: 1px solid light-dark(#e5e7eb, #374151);">',
            f'<p style="margin: 0 0 12px 0; font-weight: 600; color: light-dark(#374151, #e5e7eb);">🖼️ {images.count()} ' + str(_('additional images uploaded')) + '</p>',
            '<div style="display: flex; flex-wrap: wrap; gap: 16px;">'
        ]

        for img in images:
            app_label = WaypointViewImage._meta.app_label
            model_name = WaypointViewImage._meta.model_name

            try:
                change_url = reverse(f'admin:{app_label}_{model_name}_change', args=[img.pk])
                manage_link = (
                    f'<a href="{change_url}" '
                    f'style="color: light-dark(#dc2626, #f87171); font-size: 0.75rem; font-weight: 500; text-decoration: none;" '
                    f'target="_blank">🗑️ {_("Manage")}</a>'
                )
            except Exception:
                manage_link = ''

            img_url = f"/stream_minio_resource/?tour={img.waypoint.tour.pk}&waypoint={img.waypoint.pk}&file={img.image.name}"

            html_parts.append(f'''
                <div style="width: 200px; border: 1px solid light-dark(#e5e7eb, #374151); border-radius: 8px;
                    overflow: hidden; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);">
                <img src="data:image/gif;base64,R0lGODlhAQABAAAAACwAAAAAAQABAAA="
                    data-waypoint-lazy-src="{img_url}"
                    alt="Additional image"
                    onclick="window.open('{img_url}', '_blank')"
                    style="width: 100%; height: 160px; object-fit: cover; cursor: pointer; background: light-dark(#f3f4f6, #111827);"
                    title="{_('Click to view image in full screen')}"
                    loading="lazy"
                    decoding="async"
                />
                <div style="padding: 8px; background: light-dark(#ffffff, #1f2937); display: flex;
                        justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.75rem; color: light-dark(#6b7280, #9ca3af);">ID: {img.pk}</span>
                        {manage_link}
                    </div>
                </div>
            ''')

        html_parts.append('</div></div>')
        return mark_safe(''.join(html_parts))
    
    formfield_overrides = {
        PlainLocationField: {"widget": LocationWidget},
    }
    
    # def has_delete_permission(self, request, obj=None):
    #     has_permission = super().has_delete_permission(request, obj)
    #     if not has_permission:
    #         return False
    #     if obj is None:
    #         return True
    #     if not request.user.is_superuser and obj.user != request.user:
    #         return False
    #     return True

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_view_tour(request.user, obj)
    
    
    def has_change_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_edit_tour(request.user, obj)
    
    
    def has_add_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_edit_tour(request.user, obj)
    
    
    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_edit_tour(request.user, obj)

    
    class Media:
        js = [
            'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
            'https://cdn.jsdelivr.net/simplemde/latest/simplemde.min.js',
            # 'admin/js/init_maps.js',
            'admin/js/init_markdown_editor.js',
            'admin/js/hide_waypoint_coordinates.js',
            'admin/js/preliminary_waypoint.js'
        ]
        css = {
            'all': [
                'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
                'https://cdn.jsdelivr.net/simplemde/latest/simplemde.min.css'
            ]
        }

class WaypointViewImageAdmin(ModelAdmin):

    list_display = ('id', 'waypoint', 'image_preview', 'type_of_images')
    list_filter = ('waypoint__tour',)
    search_fields = ('waypoint__title', 'waypoint__tour__title')
    
    @admin.display(description=_("Preview"))
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 4px;" />',
                obj.image.url
            )
        return _("No image")
    
    # def get_queryset(self, request):
    #     qs = super().get_queryset(request)
        
    #     if not request.user.is_superuser:
    #         qs = qs.filter(waypoint__tour__user=request.user)
        
    #     return qs
    # 
    def get_queryset(self, request):
        qs = super().get_queryset(request)
    
        visible_tours = visible_tours_queryset(
            request.user,
            Tour.objects.all(),
        )
    
        return qs.filter(waypoint__tour__in=visible_tours).distinct()

    
    # def formfield_for_foreignkey(self, db_field, request, **kwargs):
    #     if db_field.name == "waypoint":
    #         if not request.user.is_superuser:
    #             kwargs["queryset"] = Waypoint.objects.filter(tour__user=request.user)
        
    #     return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "waypoint":
            visible_tours = visible_tours_queryset(
                request.user,
                Tour.objects.all(),
            )
    
            kwargs["queryset"] = Waypoint.objects.filter(
                tour__in=visible_tours,
            ).distinct()
    
        return super().formfield_for_foreignkey(db_field, request, **kwargs) 
    
    
    # def has_delete_permission(self, request, obj=None):
    #     has_permission = super().has_delete_permission(request, obj)
    #     if not has_permission:
    #         return False
    #     if obj is None:
    #         return True
    #     if not request.user.is_superuser and obj.waypoint.tour.user != request.user:
    #         return False
    #     return True

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_view_tour(request.user, obj.waypoint.tour)
    
    
    def has_change_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_edit_tour(request.user, obj.waypoint.tour)
    
    
    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if not has_permission:
            return False
    
        if obj is None:
            return True
    
        return can_edit_tour(request.user, obj.waypoint.tour)


admin.site.register(WaypointViewImage, WaypointViewImageAdmin)

class WaypointViewLinkAdmin(ModelAdmin):
    list_display = ('id', 'waypoint', 'link_preview')
    list_filter = ('waypoint__tour',)
    search_fields = ('waypoint__title', 'waypoint__tour__title', 'link')
    
    fieldsets = (
        (_('🔗 Link Information'), {
            'fields': ('waypoint', 'link'),
            'description': (
                '<div style="background: light-dark(#dbeafe, #1e3a8a); padding: 12px; border-radius: 6px; '
                'margin-bottom: 12px; border-left: 4px solid light-dark(#3b82f6, #60a5fa); '
                'color: light-dark(#1e3a8a, #dbeafe);">'
                '<strong>🔗 ' + str(_('Add Link:')) + '</strong> ' +
                str(_('Insert external URLs to enrich this point of interest (e.g.: official website, Wikipedia, YouTube video)')) +
                '</div>'
            )
        }),
    )
    
    @admin.display(description=_("🔗 Link"))
    def link_preview(self, obj):
        if obj.link:
            return format_html(
                '<a href="{}" target="_blank" style="color: #3b82f6; text-decoration: none;">{}</a>',
                obj.link,
                obj.link[:50] + '...' if len(obj.link) > 50 else obj.link
            )
        return _("No link")
    
    # def get_queryset(self, request):
    #     qs = super().get_queryset(request)
        
    #     if not request.user.is_superuser:
    #         qs = qs.filter(waypoint__tour__user=request.user)
        
    #     return qs

    def get_queryset(self, request):
        qs = super().get_queryset(request)
    
        visible_tours = visible_tours_queryset(
            request.user,
            Tour.objects.all(),
        )
    
        return qs.filter(waypoint__tour__in=visible_tours).distinct()

    
    # def formfield_for_foreignkey(self, db_field, request, **kwargs):
    #     if db_field.name == "waypoint":
    #         if not request.user.is_superuser:
    #             kwargs["queryset"] = Waypoint.objects.filter(tour__user=request.user)
        
    #     return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "waypoint":
            visible_tours = visible_tours_queryset(
                request.user,
                Tour.objects.all(),
            )
    
            kwargs["queryset"] = Waypoint.objects.filter(
                tour__in=visible_tours,
            ).distinct()
    
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    
    # def has_delete_permission(self, request, obj=None):
    #     has_permission = super().has_delete_permission(request, obj)
    #     if not has_permission:
    #         return False
    #     if obj is None:
    #         return True
    #     if not request.user.is_superuser and obj.waypoint.tour.user != request.user:
    #         return False
    #     return True

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_view_tour(request.user, obj.waypoint.tour)
    
    
    def has_change_permission(self, request, obj=None):
        if obj is None:
            return True
        return can_edit_tour(request.user, obj.waypoint.tour)
    
    
    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if not has_permission:
            return False
    
        if obj is None:
            return True
    
        return can_edit_tour(request.user, obj.waypoint.tour)

         
admin.site.register(WaypointViewLink, WaypointViewLinkAdmin)
