from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display
import requests
import os
from dotenv import load_dotenv
from ..models import CustomUser

load_dotenv()

def get_community_server_base_url():
    configured_url = os.getenv("COMMUNITY_SERVER_URL", "").strip()
    if configured_url:
        return configured_url.rstrip("/")

    legacy_value = os.getenv("COMMUNITY_SERVER", "").strip()
    if legacy_value.startswith(("http://", "https://")):
        return legacy_value.rstrip("/")

    return f"http://{legacy_value}".rstrip("/")

@admin.register(CustomUser)
class CustomUserAdmin(ModelAdmin, UserAdmin):
    model = CustomUser
    list_filter = ()
    
    compressed_fields = True
    warn_unsaved_form = True
    
    def get_list_display(self, request):
        if request.user.is_superuser:
            return ('username', 'email', 'full_name_display', 'city', 'is_staff', 'is_superuser')
        return ('username', 'email', 'full_name_display', 'city')
    
    @display(description=_('Full Name'), label=True)
    def full_name_display(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or "-"
    
    search_fields = ('username', 'email', 'first_name', 'last_name', 'city')
    
    exclude = ('groups', 'user_permissions', 'last_login', 'date_joined')

    fieldsets = (
        (_('Account Credentials'), {
            'fields': ('username', 'password', 'password_reset_action'),
            'description': _('Login credentials for the user account'),
            'classes': ('tab',),
        }),
        (_('Personal Information'), {
            'fields': ('first_name', 'last_name', 'email', 'city', 'description'),
            'description': _('Personal information and profile details'),
            'classes': ('tab',),
        }),
    )
    
    superuser_fieldsets = (
        (_('Account Credentials'), {
            'fields': ('username', 'password', 'password_reset_action'),
            'description': _('Login credentials for the user account'),
            'classes': ('tab',)
        }),
        (_('Personal Information'), {
            'fields': (_('first_name'), _('last_name'), 'email', _('city'), _('description')),
            'description': _('Personal information and profile details'),
            'classes': ('tab',)
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
            'description': _('User permissions and access level'),
            'classes': ('tab',)
        }),
    )
    
    readonly_fields = ('password_reset_action',)

    def password_reset_action(self, obj):
        if obj and obj.pk and obj.email:
            reset_url = reverse('admin:customuser_reset_password', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" style="padding: 8px 12px; background-color: #0c4b33; '
                'color: white; text-decoration: none; border-radius: 4px; display: inline-block; '
                'font-weight: 500;">{}</a>',
                reset_url,
                _('Send Password Reset Email')
            )
        return "-"
    
    password_reset_action.short_description = _('Password Reset')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:user_id>/reset-password/',
                self.admin_site.admin_view(self.reset_password_view),
                name='customuser_reset_password',
            ),
        ]
        return custom_urls + urls

    def reset_password_view(self, request, user_id):
        try:
            user = self.get_object(request, user_id)
            
            if not user:
                self.message_user(
                    request,
                    _("User not found."),
                    level=messages.ERROR
                )
                return redirect('admin:xr_tour_guide_core_customuser_change', user_id)

            
            if not user.email:
                self.message_user(
                    request,
                    _("User does not have an email address."),
                    level=messages.ERROR
                )
                return redirect('admin:xr_tour_guide_core_customuser_change', user_id)


            response = requests.post(
                # f"http://{os.getenv('COMMUNITY_SERVER')}/reset-password/",
                f"{get_community_server_base_url()}/reset-password/",
                json={'email': user.email},
                timeout=5,
                headers={
                    "x-api-key": os.getenv('IDP_API_KEY'),
                    "x-api-secret": os.getenv('IDP_API_SECRET'),
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                self.message_user(
                    request,
                    _("Password reset email sent successfully to {email}").format(email=user.email),
                    level=messages.SUCCESS
                )
            elif response.status_code == 404:
                self.message_user(
                    request,
                    _("Email not found in Community Server."),
                    level=messages.ERROR
                )
            elif response.status_code == 400:
                self.message_user(
                    request,
                    _("Email already verified or invalid request."),
                    level=messages.WARNING
                )
            else:
                error_detail = response.json().get("detail", _("Unknown error"))
                self.message_user(
                    request,
                    _("Error sending password reset email: {error}").format(error=error_detail),
                    level=messages.ERROR
                )

        except requests.exceptions.Timeout:
            self.message_user(
                request,
                _("Connection timeout with Community Server. Please try again."),
                level=messages.ERROR
            )
        except requests.exceptions.ConnectionError:
            self.message_user(
                request,
                _("Cannot connect to Community Server. Please check if the server is running."),
                level=messages.ERROR
            )
        except Exception as e:
            print(f"Error in password reset: {str(e)}", flush=True)
            self.message_user(
                request,
                _("Error sending password reset email: {error}").format(error=str(e)),
                level=messages.ERROR
            )
        
        return redirect('admin:xr_tour_guide_core_customuser_change', user_id)


    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return self.superuser_fieldsets
        return self.fieldsets

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(id=request.user.id)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj is not None and obj == request.user

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj is None or obj == request.user

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj == request.user:
            return False
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        
        if not change:
            super().save_model(request, obj, form, change)
            return
        
        print(_("Saving user - synchronizing with Community Server"), flush=True)
        
        try:
            payload = {
                "email": obj.email,
                "username": obj.username,
                "firstName": obj.first_name,
                "lastName": obj.last_name,
                "city": obj.city,
                "description": obj.description,
            }

            auth_token = request.session.get('cs_token')
            
            if not auth_token:
                print(_("No authentication token found"), flush=True)
                self.message_user(
                    request,
                    _("Connection error with Community Server: No authentication token"),
                    level=messages.ERROR
                )
                return
            
            if not auth_token.startswith('Bearer '):
                auth_token = f"Bearer {auth_token}"

            response = requests.post(
                # f"http://{os.getenv('COMMUNITY_SERVER')}/update_profile",
                f"{get_community_server_base_url()}/update_profile",
                json=payload,
                timeout=5,
                headers={"Authorization": auth_token}
            )

            if response.status_code == 200:
                super().save_model(request, obj, form, change)
                self.message_user(
                    request,
                    _("User successfully synchronized with Community Server."),
                    level=messages.SUCCESS
                )
            else:
                error_detail = response.json().get("detail", _("Unknown error"))
                self.message_user(
                    request,
                    _("Error synchronizing with Community Server: {error}").format(error=error_detail),
                    level=messages.ERROR
                )

        except requests.exceptions.Timeout:
            self.message_user(
                request,
                _("Connection timeout with Community Server. Please try again."),
                level=messages.ERROR
            )
        except requests.exceptions.ConnectionError:
            self.message_user(
                request,
                _("Cannot connect to Community Server. Please check if the server is running."),
                level=messages.ERROR
            )
        except Exception as e:
            print(f"Error syncing with Community Server: {str(e)}", flush=True)
            self.message_user(
                request,
                _("Connection error with Community Server: {error}").format(error=str(e)),
                level=messages.ERROR
            )