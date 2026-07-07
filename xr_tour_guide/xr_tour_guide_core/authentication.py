from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
import requests
import os
from dotenv import load_dotenv

load_dotenv()
User = get_user_model()

def get_community_server_base_url():
    configured_url = os.getenv("COMMUNITY_SERVER_URL", "").strip()
    if configured_url:
        return configured_url.rstrip("/")

    legacy_value = os.getenv("COMMUNITY_SERVER", "").strip()
    if legacy_value.startswith(("http://", "https://")):
        return legacy_value.rstrip("/")

    return f"http://{legacy_value}".rstrip("/")

class JWTFastAPIAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]

        try:
            response = requests.post(
                # f"http://{os.getenv('COMMUNITY_SERVER')}/api/verify/",
                f"{get_community_server_base_url()}/api/verify/",
                data={"token": token},
                headers={
                    "x-api-key": os.getenv('IDP_API_KEY'),
                    "x-api-secret": os.getenv('IDP_API_SECRET')
                }
            )

            if response.status_code == 401:
                raise AuthenticationFailed("Service not authorized")
            
            if response.status_code != 200:
                raise AuthenticationFailed("Invalid token")

            payload = response.json()
            username = payload.get("username")
            if not username:
                raise AuthenticationFailed("Invalid token payload")

        except requests.RequestException as e:
            raise AuthenticationFailed("Token verification failed")

        try:
            user = User.objects.get(username=username)
            user.email = payload.get("email", user.email)
            user.first_name = payload.get("name", user.first_name)
            user.last_name = payload.get("surname", user.last_name)
            user.city = payload.get("city", user.city) or "Not provided"
            user.description = payload.get("description", user.description) or "Not provided"
            user.save()
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=username,
                email=payload.get("email", ""),
                first_name=payload.get("name", ""),
                last_name=payload.get("surname", ""),
                city=payload.get("city", "") or "Not provided",
                description=payload.get("description", "") or "Not provided"
            )
            user.set_unusable_password()
            user.is_staff = True
            group_name = 'User'
            try:
                group = Group.objects.get(name=group_name)
                user.groups.add(group)
            except Group.DoesNotExist:
                pass
            user.save()

        if hasattr(request, 'session'):
            request.session["cs_token"] = token

        return (user, None)