from django.shortcuts import render, redirect
from xr_tour_guide_core.models import Tour
import requests
from django.contrib.auth import get_user_model, login as django_login
from django.contrib.auth.models import Group
from django.http import HttpResponse, JsonResponse
from dotenv import load_dotenv
import os
import json
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from xr_tour_guide_core.models import CustomUser as User

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

def extract_error_message(response, default_message="Login failed"):
    try:
        data = response.json()
        return data.get("detail") or data.get('message') or default_message
    except ValueError:
        text = (response.text or "").strip()
        if text:
            return f"{default_message}: {text[:300]}"
        return default_message

def get_idp_headers():
    api_key = os.getenv('IDP_API_KEY')
    api_secret = os.getenv('IDP_API_SECRET')
    
    return {
        "x-api-key": api_key,
        "x-api-secret": api_secret,
        "Content-Type": "application/json"
    }

def landing_page(request):
    tours = Tour.objects.filter(parent_tours__isnull=True)[:6]
    return render(request, 'xr_tour_guide_public/landing_page/landing_page.html', context={'tours': tours})

def register_page(request):
    return render(request, "xr_tour_guide_public/register.html")

def login(request):
    if request.method == "POST":
        email = request.POST.get('email', None)
        password = request.POST.get('password', None)
        
        if not email or "@" not in email:
            context = {
                "error": "Email required",
                "GOOGLE_CLIENT_ID": os.getenv('GOOGLE_CLIENT_ID', '')
            }
            return render(request, "account/login.html", context)
        
        if not password:
            context = {
                "error": "Password required",
                "GOOGLE_CLIENT_ID": os.getenv('GOOGLE_CLIENT_ID', '')
            }
            return render(request, "account/login.html", context)
        
        response = requests.post(
            # f"http://{os.getenv('COMMUNITY_SERVER')}/api/token/",
            f"{get_community_server_base_url()}/api/token/",
            json={'email': email, 'password': password},
            headers=get_idp_headers(),
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            user_data = data["user"]
            
            try:
                user = User.objects.get(email=email)
                user.username = user_data["username"]
                user.first_name = user_data.get("name", "")
                user.last_name = user_data.get("surname", "")
                user.city = user_data.get("city", "") or "Not provided"
                user.description = user_data.get("description", "")  or "Not provided"
            except User.DoesNotExist:
                user = User.objects.create_user(
                    username=user_data["username"],
                    email=email,
                    first_name=user_data.get("name", ""),
                    last_name=user_data.get("surname", ""),
                    city=user_data.get("city", "")  or "Not provided",
                    description=user_data.get("description", "")  or "Not provided"
                )
            
            user.is_staff = True
            group_name = 'User'
            group = Group.objects.get(name=group_name)
            user.groups.add(group)
            user.save()

            user.backend = 'django.contrib.auth.backends.ModelBackend'
            django_login(request, user)

            request.session["cs_token"] = data["access"]
            return redirect(settings.LOGIN_REDIRECT_URL)
        else:
            context = {
                "error": extract_error_message(
                    response,
                    default_message=f"Login failed with status {response.status_code}",
                ),
                "GOOGLE_CLIENT_ID": os.getenv('GOOGLE_CLIENT_ID', '')
            }
            return render(request, "account/login.html", context)

    context = {
        "GOOGLE_CLIENT_ID": os.getenv('GOOGLE_CLIENT_ID', '')
    }
    return render(request, "account/login.html", context)

@require_http_methods(["POST"])
def google_login(request):
    
    try:
        raw_body = request.body.decode('utf-8')
        
        data = json.loads(raw_body)
        
        id_token = data.get('id_token')
        
        if not id_token:
            return JsonResponse(
                {"detail": "ID token required"},
                status=400
            )
        
        # idp_url = f"http://{os.getenv('COMMUNITY_SERVER')}/api/google-login/"
        idp_url = f"{get_community_server_base_url()}/api/google-login/"
        
        response = requests.post(
            idp_url,
            json={'id_token': id_token},
            headers=get_idp_headers(),
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            user_data = data["user"]
            
            try:
                user = User.objects.get(email=user_data["email"])
                user.username = user_data["username"]
                user.first_name = user_data.get("name", "")
                user.last_name = user_data.get("surname", "")
                user.city = user_data.get("city", "Not provided") or "Not provided"
                user.description = user_data.get("description", "Not provided") or "Not provided"
                user.is_staff = True
            except User.DoesNotExist:
                user = User.objects.create_user(
                    username=user_data["username"],
                    email=user_data["email"],
                    first_name=user_data.get("name", ""),
                    last_name=user_data.get("surname", ""),
                    city=user_data.get("city", "Not provided") or "Not provided",
                    description=user_data.get("description", "Not provided") or "Not provided",
                    is_staff=True
                )
            
            group_name = 'User'
            try:
                group = Group.objects.get(name=group_name)
                user.groups.add(group)
            except Group.DoesNotExist:
                print(f" Warning: Group '{group_name}' does not exist")
            
            user.save()
            print(f" User saved: {user.username}")
            
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            django_login(request, user)
            
            request.session["cs_token"] = data["access"]
            
            return JsonResponse({
                "success": True,
                "redirect": settings.LOGIN_REDIRECT_URL
            }, status=200)
            
        else:
            error_data = response.json() if response.content else {"detail": "Authentication failed"}
            return JsonResponse(
                {"detail": error_data.get("detail", "Authentication failed")},
                status=response.status_code
            )
            
    except requests.exceptions.RequestException as e:
        return JsonResponse(
            {"detail": "Connection error to authentication server"},
            status=500
        )
    except json.JSONDecodeError as e:
        return JsonResponse(
            {"detail": "Invalid JSON in request"},
            status=400
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse(
            {"detail": f"Server error: {str(e)}"},
            status=500
        )
    
def register(request):
    if request.method == "POST":
        data = json.loads(request.body)
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
        name = data.get("firstName")
        surname = data.get("lastName")
        description = data.get("description")
        city = data.get("city")

        try:
            response = requests.post(
                # f"http://{os.getenv('COMMUNITY_SERVER')}/api_register/",
                f"{get_community_server_base_url()}/api_register/",
                json={
                    "username": username,
                    "email": email,
                    "password": password,
                    "firstName": name,
                    "lastName": surname,
                    "description": description,
                    "city": city
                },
                headers=get_idp_headers(),
                timeout=10
            )
            
        except requests.exceptions.RequestException as e:
            print(f"Registration request error: {e}")
            return JsonResponse(
                {"detail": "Connection error to API server."},
                status=500
            )

        if response.status_code in (201, 202):
            try:
                data = response.json()
                print(f"Registration response: {data}")
            except ValueError:
                data = {"message": "Registration completed successfully"}
            return JsonResponse(data, status=response.status_code)

        try:
            error_data = response.json()
        except ValueError:
            error_data = {"detail": response.text}

        return JsonResponse(error_data, status=response.status_code)

    return render(request, "xr_tour_guide_public/register.html")

def send_verification_email(request):
    email = request.POST.get('email')
    
    try:
        response = requests.post(
            # f"http://{os.getenv('COMMUNITY_SERVER')}/resend-verification/",
            f"{get_community_server_base_url()}/resend-verification/",
            json={'email': email},
            headers=get_idp_headers()
        )
    except requests.exceptions.RequestException as e:
        print(f"Verification email request error: {e}")
        return HttpResponse("Connection error", status=500)
    
    if response.status_code == 200:
        return HttpResponse("Verification email sent successfully", status=response.status_code)
    elif response.status_code == 404:
        return HttpResponse("Email not found", status=response.status_code)
    elif response.status_code == 400:
        return HttpResponse("Email already verified", status=response.status_code)
    elif response.status_code == 429:
        try:
            payload = response.json()
            detail = payload.get("detail", "Too many requests. Please try again later.")
        except ValueError:
            detail = "Too many requests. Please try again later."
        return HttpResponse(detail, status=response.status_code)
    else:
        return HttpResponse("Error sending email", status=response.status_code)

def reset_password(request):
    email = request.POST.get('email')

    try:
        response = requests.post(
            # f"http://{os.getenv('COMMUNITY_SERVER')}/reset-password/",
            f"{get_community_server_base_url()}/reset-password/",
            json={'email': email},
            headers=get_idp_headers()
        )
    except requests.exceptions.RequestException as e:
        print(f"Reset password request error: {e}")
        return HttpResponse("Connection error", status=500)
    
    if response.status_code == 200:
        return HttpResponse("Password reset email sent successfully", status=response.status_code)
    elif response.status_code == 404:
        return HttpResponse("Email not found", status=response.status_code)
    elif response.status_code == 400:
        return HttpResponse("Email already verified", status=response.status_code)
    else:
        return HttpResponse("Error sending email", status=response.status_code)

@csrf_exempt
@require_http_methods(["POST"])
def google_mobile_login(request):
    print("google_mobile_login HIT", request.method, request.path, flush=True)
    try:
        raw_body = request.body.decode("utf-8")
        data = json.loads(raw_body)
        id_token = data.get("id_token")

        if not id_token:
            return JsonResponse({"detail": "ID token required"}, status=400)

        idp_url = f"{get_community_server_base_url()}/api/google-login/"

        response = requests.post(
            idp_url,
            json={"id_token": id_token},
            headers=get_idp_headers(),
            timeout=10,
        )

        if response.status_code != 200:
            error_data = response.json() if response.content else {"detail": "Authentication failed"}
            return JsonResponse(
                {"detail": error_data.get("detail", "Authentication failed")},
                status=response.status_code,
            )

        data = response.json()
        user_data = data["user"]

        try:
            user = User.objects.get(email=user_data["email"])
            user.username = user_data["username"]
            user.first_name = user_data.get("name", "")
            user.last_name = user_data.get("surname", "")
            user.city = user_data.get("city", "Not provided") or "Not provided"
            user.description = user_data.get("description", "Not provided") or "Not provided"
            user.is_staff = True
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=user_data["username"],
                email=user_data["email"],
                first_name=user_data.get("name", ""),
                last_name=user_data.get("surname", ""),
                city=user_data.get("city", "Not provided") or "Not provided",
                description=user_data.get("description", "Not provided") or "Not provided",
                is_staff=True,
            )

        try:
            group = Group.objects.get(name="User")
            user.groups.add(group)
        except Group.DoesNotExist:
            print("Warning: Group 'User' does not exist")

        user.save()

        return JsonResponse(
            {
                "access": data["access"],
                "refresh": data["refresh"],
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "name": user.first_name,
                    "surname": user.last_name,
                    "city": user.city,
                    "description": user.description,
                },
            },
            status=200,
        )

    except requests.exceptions.RequestException:
        return JsonResponse(
            {"detail": "Connection error to authentication server"},
            status=500,
        )
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON in request"}, status=400)
    except Exception as e:
        return JsonResponse({"detail": f"Server error: {str(e)}"}, status=500)
    
    
@csrf_exempt
@require_http_methods(["POST"])
def apple_mobile_login(request):
    print("apple_mobile_login HIT", request.method, request.path, flush=True)
    try:
        raw_body = request.body.decode("utf-8")
        data = json.loads(raw_body)
        
        identity_token = data.get("identity_token")
        authorization_code = data.get("authorization_code")
        given_name = data.get("given_name", "")
        family_name = data.get("family_name", "")
        email = data.get("email")
        
        if not identity_token:
            return JsonResponse({"detail": "Identity token required"}, status=400)
        
        if not authorization_code:
            return JsonResponse({"detail": "Authorization code required"}, status=400)
        
        idp_url = f"{get_community_server_base_url()}/api/apple-login/"

        response = requests.post(
            idp_url,
            json={
                "identity_token": identity_token,
                "authorization_code": authorization_code,
                "given_name": given_name,
                "family_name": family_name,
                "email": email
            },
            headers=get_idp_headers(),
            timeout=10,
        )

        if response.status_code != 200:
            error_data = response.json() if response.content else {"detail": "Authentication failed"}
            return JsonResponse(
                {"detail": error_data.get("detail", "Authentication failed")},
                status=response.status_code,
            )

        data = response.json()
        user_data = data["user"]

        try:
            user = User.objects.get(email=user_data["email"])
            user.username = user_data["username"]
            user.first_name = user_data.get("name", "")
            user.last_name = user_data.get("surname", "")
            user.city = user_data.get("city", "Not provided") or "Not provided"
            user.description = user_data.get("description", "Not provided") or "Not provided"
            user.is_staff = False
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=user_data["username"],
                email=user_data["email"],
                first_name=user_data.get("name", ""),
                last_name=user_data.get("surname", ""),
                city=user_data.get("city", "Not provided") or "Not provided",
                description=user_data.get("description", "Not provided") or "Not provided",
                is_staff=False,
            )

        try:
            group = Group.objects.get(name="User")
            user.groups.add(group)
        except Group.DoesNotExist:
            print("Warning: Group 'User' does not exist")

        user.save()

        return JsonResponse(
            {
                "access": data["access"],
                "refresh": data["refresh"],
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "name": user.first_name,
                    "surname": user.last_name,
                    "city": user.city,
                    "description": user.description,
                },
            },
            status=200,
        )

    except requests.exceptions.RequestException:
        return JsonResponse(
            {"detail": "Connection error to authentication server"},
            status=500,
        )
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON in request"}, status=400)
    except Exception as e:
        return JsonResponse({"detail": f"Server error: {str(e)}"}, status=500)