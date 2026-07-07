from django.contrib import admin
from django import forms
import nested_admin
from unfold.admin import ModelAdmin
from ..models import Tour
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.db import models
from ..forms.tour_forms import TourForm
from .waypoint_admin import WaypointAdmin
from django.contrib.admin.views.main import ChangeList
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from ..services.tour_portability import TourPortabilityService, TourPortabilityError
from ..forms.tour_import_form import TourImportForm
import tempfile
from pathlib import Path
import time
from django.utils.text import slugify
from xr_tour_guide.tasks import call_api_and_save, generate_offline_bundle

class TourAdmin(nested_admin.NestedModelAdmin, ModelAdmin):
    show_facets = admin.ShowFacets.ALLOW
    hide_ordering_field = True
    compressed_fields = True
    
    change_form_template = "admin/xr_tour_guide_core/tour/change_form.html"
    list_display = ('title', 'place', 'category', 'language', 'status_badge', 'creation_time', 'user', 'actions_buttons')
    readonly_fields = ['user', 'creation_time', 'status_info', 'status_badge', 'status', 'license_notice']
    list_filter = ['category', 'language', 'status', 'place', 'creation_time']
    search_fields = ('title', 'subtitle', 'description', 'place')
    date_hierarchy = 'creation_time'
    form = TourForm
    inlines = [WaypointAdmin]
    
    fieldsets = (
        (None, {
            'fields': ('status_info',),
            'classes': ('wide',),
        }),
        (_('🎯 Main Information'), {
            'fields': ('title', 'subtitle', 'category', 'language'),
        }),
        (_('📝 Full Description'), {
            'fields': ('description',),
        }),
        (_('📍 Location and Area'), {
            'fields': ('place', 'coordinates'),
        }),
        (_('🖼️ Cover Image'), {
            'fields': ('license_notice', 'default_image',),
        }),
        (_('🔗 Internal Tours (Optional)'), {
            'fields': ('sub_tours',),
            'classes': ('collapse',),
        }),
        (_('⚙️ System Information'), {
            'fields': ('user', 'creation_time', 'status', 'is_subtour'),
            'classes': ('collapse',),
            'description': _('Technical information automatically managed by the system')
        }),
    )

    formfield_overrides = {
        models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    }
    
    widgets = {
        'is_subtour': forms.HiddenInput()
    }

    class Media:
        js = [
            'https://code.jquery.com/jquery-3.6.0.min.js', 
            # 'admin/js/init_maps.js',
            'admin/js/init_markdown_editor.js',
            'admin/js/hide_waypoint_coordinates.js',
            # 'admin/js/refresh_subtours_checkboxes.js',
            'admin/js/fix_minio_preview.js',
            'admin/js/loader.js',
            'admin/js/subtour_popup.js',
        ]
        css = {
            'all': [
                'admin/css/subtour_improved.css',
            ]
        }
        
    @admin.display(description=_("Export"))
    def export_button(self, obj):
        url = reverse("admin:xr_tour_guide_core_tour_export", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" data-loader-link="true" '
            'data-loader-download="true" '
            'data-loader-keep-visible="true" '
            'data-loader-text="Preparing export..." '
            'data-loader-subtext="Please wait while the tour archive is being generated." '
            'style="padding:4px 8px; border-radius:6px; background:#2563eb; color:white; text-decoration:none;">📦 Export</a>',
            url,
        )
        
    @admin.display(description=_("License"))
    def license_notice(self, obj):
        return mark_safe(f'''
            <div style="
                display: flex;
                align-items: flex-start;
                gap: 12px;
                background: light-dark(#eff6ff, #1e3a5f);
                border: 1px solid light-dark(#bfdbfe, #2d5a9e);
                border-left: 4px solid light-dark(#3b82f6, #60a5fa);
                border-radius: 8px;
                padding: 14px 16px;
                margin: 4px 0 8px 0;
                color: light-dark(#1e3a8a, #bfdbfe);
                font-size: 0.875rem;
                line-height: 1.6;
            ">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"
                     viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                     style="flex-shrink:0; margin-top:2px; opacity:.8;">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <div>
                    <div style="font-weight: 700; margin-bottom: 4px; font-size: 0.9375rem;">
                        {_("Content licensed under CC BY-NC 4.0")}
                    </div>
                    <div style="opacity: .85;">
                        {_("The images and multimedia content associated with this tour are protected under the")}
                        <a href="https://creativecommons.org/licenses/by-nc/4.0/"
                           target="_blank"
                           rel="noopener noreferrer"
                           style="
                               color: light-dark(#2563eb, #93c5fd);
                               font-weight: 600;
                               text-decoration: none;
                               border-bottom: 1px solid light-dark(#93c5fd, #60a5fa);
                           ">
                            Creative Commons Attribution-NonCommercial 4.0 International
                        </a>
                        {_("license. Reproduction, distribution or commercial use without explicit written authorization from the rights holder is strictly prohibited.")}
                    </div>
                    <div style="
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        margin-top: 10px;
                        flex-wrap: wrap;
                    ">
                        <span style="
                            display: inline-flex; align-items: center; gap: 4px;
                            padding: 3px 10px; border-radius: 20px;
                            background: light-dark(#dbeafe, #1e40af);
                            color: light-dark(#1d4ed8, #bfdbfe);
                            font-size: 0.75rem; font-weight: 700; letter-spacing: .04em;
                        ">© {_("Attribution required")}</span>
                        <span style="
                            display: inline-flex; align-items: center; gap: 4px;
                            padding: 3px 10px; border-radius: 20px;
                            background: light-dark(#fee2e2, #7f1d1d);
                            color: light-dark(#dc2626, #fca5a5);
                            font-size: 0.75rem; font-weight: 700; letter-spacing: .04em;
                        ">⊘ {_("No commercial use")}</span>
                        <span style="
                            display: inline-flex; align-items: center; gap: 4px;
                            padding: 3px 10px; border-radius: 20px;
                            background: light-dark(#d1fae5, #065f46);
                            color: light-dark(#059669, #6ee7b7);
                            font-size: 0.75rem; font-weight: 700; letter-spacing: .04em;
                        ">✓ {_("Sharing allowed")}</span>
                    </div>
                </div>
            </div>
        ''')

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        status_colors = {
            'READY': '#3b82f6',
            'ENQUEUED': '#f59e0b',
            'BUILDING': '#8b5cf6',
            'FAILED': '#ef4444',
        }
        status_labels = {
            'READY': _('✅ Ready'),
            'ENQUEUED': _('⏳ Queued'),
            'BUILDING': _('🔨 Building'),
            'FAILED': _('❌ Error'),
        }
        color = status_colors.get(obj.status, '#6b7280')
        label = status_labels.get(obj.status, obj.status)
        
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; '
            'border-radius: 12px; font-size: 0.75rem; font-weight: 600; '
            'display: inline-block;">{}</span>',
            color, label
        )
    
    @admin.display(description=_("Tour Status"))
    def status_info(self, obj):
        status_info = {
            "READY": {
                "bg_light": "#dbeafe",
                "bg_dark": "#1e3a8a",
                "border_light": "#3b82f6",
                "border_dark": "#60a5fa",
                "title": _("✅ Ready for Publication"),
                "message": _("The tour is complete and ready to be published."),
                "action": _("It will be processed and published automatically."),
            },
            "ENQUEUED": {
                "bg_light": "#fef3c7",
                "bg_dark": "#78350f",
                "border_light": "#f59e0b",
                "border_dark": "#fbbf24",
                "title": _("⏳ Queued"),
                "message": _("The tour is queued for processing."),
                "action": _("Please wait, it will be processed shortly. Do not modify during this phase."),
            },
            "BUILDING": {
                "bg_light": "#f3e8ff",
                "bg_dark": "#581c87",
                "border_light": "#8b5cf6",
                "border_dark": "#a78bfa",
                "title": _("🔨 Building"),
                "message": _("The tour is being processed."),
                "action": _("Do not modify the tour during this phase. The process may take a few minutes."),
            },
            "FAILED": {
                "bg_light": "#fee2e2",
                "bg_dark": "#7f1d1d",
                "border_light": "#ef4444",
                "border_dark": "#f87171",
                "title": _("❌ Error"),
                "message": _("An error occurred while processing the tour."),
                "action": _("Check the entered data or contact support."),
            },
            "BUILT": {
                "bg_light": "#d1fae5",
                "bg_dark": "#065f46",
                "border_light": "#10b981",
                "border_dark": "#34d399",
                "title": _("✅ Ready for Use"),
                "message": _("Model successfully trained and ready to be used."),
                "action": _("You can start serving the tour to visitors."),
            },
        }
        
        info = status_info.get(obj.status)
        
        is_locked = obj.status in ['BUILDING', 'SERVING', 'ENQUEUED']
        lock_notice = ''
        if is_locked:
            lock_notice = f'''
                <div style="
                    background: light-dark(#fee2e2, #7f1d1d);
                    padding: 12px;
                    border-radius: 8px;
                    margin-top: 12px;
                    border-left: 4px solid light-dark(#ef4444, #f87171);
                    color: light-dark(#7f1d1d, #fecaca);
                ">
                    <strong>{_("🔒 Tour Locked:")}</strong> {_("You cannot modify the tour in this state.")}
                </div>
            '''
        
        return mark_safe(
            f'''<div style="
                background: light-dark({info["bg_light"]}, {info["bg_dark"]});
                padding: 16px;
                border-radius: 8px;
                border-left: 4px solid light-dark({info["border_light"]}, {info["border_dark"]});
                margin-bottom: 20px;
                color: light-dark(#1f2937, #f9fafb);
            ">
                <h3 style="margin: 0 0 8px 0; font-size: 1.125rem; font-weight: 600;">{info["title"]}</h3>
                <p style="margin: 0 0 8px 0; font-weight: 500;">{info["message"]}</p>
                <p style="margin: 0; font-size: 0.875rem; opacity: 0.8;">{info["action"]}</p>
                {lock_notice}
            </div>'''
        )
        
    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        def form_wrapper(*args, **kw):
            kw["request"] = request
            return Form(*args, **kw)

        return form_wrapper

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "sub_tours":
            tour_id = request.resolver_match.kwargs.get("object_id")
            available = Tour.objects.filter(
                is_subtour=True, 
                category="INDOOR", 
                parent_tours__isnull=True
            )
            if tour_id:
                tour = Tour.objects.get(id=tour_id)
                associated = tour.sub_tours.all()
                kwargs["queryset"] = (associated | available).distinct()
            else:
                kwargs["queryset"] = available
            
            return super().formfield_for_manytomany(db_field, request, **kwargs)

        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if not request.user.is_superuser:
            qs = qs.filter(user=request.user)

        return qs
    
    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, extra_context)

    def get_changelist(self, request, **kwargs):
        
        class SubtourFilteredChangeList(ChangeList):
            def get_queryset(self, request):
                qs = super().get_queryset(request)
                return qs.filter(is_subtour=False)
        
        return SubtourFilteredChangeList

    def save_model(self, request, obj, form, change):
        if not change:
            obj.user = request.user
        if change:
            obj.status = "READY"
        super().save_model(request, obj, form, change)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial['user'] = request.user.pk
        return initial

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        for subtour in form.instance.sub_tours.all():
            if not subtour.is_subtour:
                subtour.is_subtour = True
                subtour.save()
            if form.instance not in subtour.parent_tours.all():
                subtour.parent_tours.add(form.instance)

    def delete_model(self, request, obj):
        if obj.status in ['SERVING', 'BUILDING', 'ENQUEUED']:
            self.message_user(
                request, 
                _("❌ Non puoi eliminare questo tour perché è in uno stato bloccato."), 
                level=messages.ERROR
            )
        else:
            super().delete_model(request, obj)
            
    def response_delete(self, request, obj_display, obj_id):
        return HttpResponseRedirect(reverse("admin:index"))
    
    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context["title"] = _("New Tour")
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        if obj and obj.status in ['BUILDING', 'SERVING', 'ENQUEUED']:
            self.message_user(
                request,
                _("❌ Non puoi modificare questo tour perché è in uno stato bloccato."),
                level=messages.ERROR
            )
            return redirect('admin:%s_%s_changelist' % (obj._meta.app_label, obj._meta.model_name))
        
        extra_context = extra_context or {}
        if obj:
            extra_context["title"] = f"Edit"
        
        return super().change_view(request, object_id, form_url, extra_context)
    
    def has_change_permission(self, request, obj=None):
        has_permission = super().has_change_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.status in ['BUILDING', 'SERVING', 'ENQUEUED']:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.status in ['SERVING', 'BUILDING', 'ENQUEUED']:
            return False
        if not request.user.is_superuser and obj.user != request.user:
            return False
        return True
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-tour/",
                self.admin_site.admin_view(self.import_tour_view),
                name="xr_tour_guide_core_tour_import",
            ),
            path(
                "<path:object_id>/export-tour/",
                self.admin_site.admin_view(self.export_tour_view),
                name="xr_tour_guide_core_tour_export",
            ),
            path(
                "<path:object_id>/build-tour/",
                self.admin_site.admin_view(self.build_tour_view),
                name="xr_tour_guide_core_tour_build",
            ),
        ]
        return custom_urls + urls

    def build_tour_view(self, request, object_id):
        tour = get_object_or_404(Tour, pk=object_id)
    
        if not request.user.is_superuser and tour.user != request.user:
            raise Http404()
    
        if tour.status != "READY":
            self.message_user(
                request,
                _("❌ This tour cannot be built because it is not READY."),
                level=messages.ERROR,
            )
            return redirect("admin:xr_tour_guide_core_tour_changelist")
    
        tour.status = "ENQUEUED"
        tour.save(update_fields=["status"])
    
        if tour.category == "GUIDE":
            generate_offline_bundle.delay(tour.id)
            message = _("📦 Offline build started.")
        else:
            call_api_and_save.apply_async(args=[tour.id], queue="api_tasks")
            message = _("🧠 Training started.")
    
        self.message_user(request, message, level=messages.SUCCESS)
    
        return redirect("admin:xr_tour_guide_core_tour_changelist")

    @admin.display(description=_("Actions"))
    def actions_buttons(self, obj):
        change_url = reverse(
            "admin:xr_tour_guide_core_tour_change",
            args=[obj.pk],
        )
    
        export_url = reverse(
            "admin:xr_tour_guide_core_tour_export",
            args=[obj.pk],
        )
    
        build_url = reverse(
            "admin:xr_tour_guide_core_tour_build",
            args=[obj.pk],
        )
    
        if obj.status == "READY":
            build_label = _("Build offline") if obj.category == "GUIDE" else _("Train")
            build_icon = "📦" if obj.category == "GUIDE" else "🧠"
    
            build_button = format_html(
                '''
                <a href="{}"
                   class="button"
                   style="display:inline-block; margin-right:4px; padding:4px 8px;
                          border-radius:6px; background:#2563eb; color:white;
                          text-decoration:none; font-size:12px; font-weight:600;">
                    {} {}
                </a>
                ''',
                build_url,
                build_icon,
                build_label,
            )
        elif obj.status == "BUILDING" or obj.status == "ENQUEUED":
            build_button = format_html(
                '''
                <span style="display:inline-block; margin-right:4px; padding:4px 8px;
                             border-radius:6px; background:#e5e7eb; color:#6b7280;
                             font-size:12px; font-weight:600;">
                    ⏳ {}
                </span>
                ''',
                _("Building…"),
            )
        else:
            build_button = ""
    
        view_button = format_html(
            '''
            <a href="{}"
               class="button"
               data-loader-link="true"
               data-loader-text="Opening tour..."
               data-loader-subtext="Loading tour data, waypoints, and resources."
               style="display:inline-block; margin-right:4px; padding:4px 8px;
                      border-radius:6px; background:#16a34a; color:white;
                      text-decoration:none; font-size:12px; font-weight:600;">
                👁 {}
            </a>
            ''',
            change_url,
            _("View"),
        )
    
        export_button = format_html(
            '''
            <a href="{}"
               class="button"
               data-loader-link="true"
               data-loader-download="true"
               data-loader-keep-visible="true"
               data-loader-text="Preparing export..."
               data-loader-subtext="Please wait while the tour archive is being generated."
               style="display:inline-block; margin-right:4px; padding:4px 8px;
                      border-radius:6px; background:#7c3aed; color:white;
                      text-decoration:none; font-size:12px; font-weight:600;">
                ⬇ {}
            </a>
            ''',
            export_url,
            _("Export"),
        )
    
        return format_html(
            '<div style="display:flex; gap:4px; flex-wrap:wrap;">{}{}{}</div>',
            build_button,
            view_button,
            export_button,
        )

    
    def export_tour_view(self, request, object_id):
        tour = get_object_or_404(Tour, pk=object_id)

        if not request.user.is_superuser and tour.user != request.user:
            raise Http404()

        service = TourPortabilityService()

        export_dir = Path(tempfile.gettempdir()) / "xr_tour_exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        archive_path = export_dir / f"tour_export_{tour.pk}_{int(time.time())}.zip"

        archive_path = Path(
            service.export_tour(
                tour,
                include_subtours=True,
                output_path=archive_path,
            )
        )

        response = FileResponse(
            open(archive_path, "rb"),
            as_attachment=True,
            filename=f"tour_export_{slugify(tour.title) or tour.pk}.zip",
        )

        response["Content-Length"] = str(archive_path.stat().st_size)
        
        dl_token = request.GET.get("dl_token")
        if dl_token:
            response.set_cookie(
                key=f"dl_{dl_token}",
                value="1",
                max_age=300,
                samesite="Lax",
            )        
        
        return response
    
    def import_tour_view(self, request):
        if request.method == "POST":
            form = TourImportForm(request.POST, request.FILES)
            if form.is_valid():
                service = TourPortabilityService()
                try:
                    tour = service.import_tour(
                        archive_file=form.cleaned_data["archive"],
                        owner=request.user,
                        create_copy=form.cleaned_data["create_copy"],
                    )
                    self.message_user(
                        request,
                        f"Tour '{tour.title}' imported successfully.",
                        level=messages.SUCCESS,
                    )
                    return redirect(
                        reverse("admin:xr_tour_guide_core_tour_change", args=[tour.pk])
                    )
                except TourPortabilityError as exc:
                    self.message_user(request, str(exc), level=messages.ERROR)
        else:
            form = TourImportForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Import Tour",
            "form": form,
        }
        return TemplateResponse(
            request,
            "admin/xr_tour_guide_core/tour/import_tour.html",
            context,
        )

admin.site.register(Tour, TourAdmin)