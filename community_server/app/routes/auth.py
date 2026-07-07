import os
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.auth import create_access_token, create_refresh_token, verify_token, verify_service_or_mobile
from app.email_utils import send_verification_email, send_forgot_password
from app.model import models
from app.model.database import SessionLocal
from app.model.models import Services
router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

VERIFICATION_TOKEN_TTL_HOURS = 24
VERIFICATION_RESEND_COOLDOWN_SECONDS = 90

def _new_verification_expiry(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.utcnow()
    return current + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS)

def _verification_is_pending(user: models.User, now: Optional[datetime] = None) -> bool:
    current = now or datetime.utcnow()
    return bool(
        user.email_verification_token and 
        user.email_verification_expires and 
        user.email_verification_expires > current
    )
    
def _seconds_until_resent_allowed(user: models.User, now: Optional[datetime] = None) -> int:
    if not user.email_verification_expires:
        return 0
    
    current = now or datetime.utcnow()
    last_sent_at = user.email_verification_expires - timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS)
    next_allowed_at = last_sent_at + timedelta(seconds=VERIFICATION_RESEND_COOLDOWN_SECONDS)
    remaining = (next_allowed_at - current).total_seconds()
    
    if remaining <= 0:
        return 0
    
    return int(remaining) + (0 if remaining.is_integer() else 1)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None

class GoogleLoginRequest(BaseModel):
    id_token: str
    
class AppleLoginRequest(BaseModel):
    identity_token: str
    authorization_code: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    email: Optional[EmailStr] = None
    
def _generate_unique_username(db: Session, email: str) -> str:
    base_username = email.split("@")[0]
    username = base_username
    counter = 1
    while db.query(models.User).filter(models.User.username == username).first():
        username = f"{base_username}{counter}"
        counter += 1
    return username

def verify_apple_identity_token(identity_token: str) -> dict:
    import requests
    from jose import jwt
    from jose.exceptions import JWTError
    
    APPLE_ISSUER = "https://appleid.apple.com"
    APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
    
    allowed_client_ids = [
        value.strip() for value in os.getenv("APPLE_CLIENT_IDS", "").split(",") if value.strip()
    ]
    
    if not allowed_client_ids:
        raise HTTPException(status_code=500, detail="Apple OAuth not configured properly")
    
    try:
        unverified_header = jwt.get_unverified_header(identity_token)
        kid = unverified_header.get("kid")
        
        keys_response = requests.get(APPLE_KEYS_URL, timeout=10)
        keys_response.raise_for_status()
        apple_keys = keys_response.json().get("keys", [])
        
        key = next((item for item in apple_keys if item.get("kid") == kid), None)
        
        if not key:
            raise HTTPException(status_code=401, detail="Invalid Apple token: key not found")
        
        last_error = None
        
        for audience in allowed_client_ids:
            try:
                return jwt.decode(
                    identity_token,
                    key,
                    algorithms=[key.get("alg", "RS256")],
                    audience = audience,
                    issuer = APPLE_ISSUER
                )
            except JWTError as e:
                last_error = e
        
        raise HTTPException(status_code=401, detail=f"Invalid Apple token: {str(last_error)}")
    
    except HTTPException as he:
        print(f"Apple verify_identity HTTP error: {he.status_code} - {he.detail}", flush=True)
        raise
    except Exception as e:
        print(f"Apple verify_identity error: {e.status_code} - {e.detail}", flush=True)
        raise HTTPException(status_code=401, detail=f"Apple token verification failed: {str(e)}")
    
@router.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    services = db.query(models.Services).all()
    return templates.TemplateResponse(
        request=request, name="login.html", context={"services": services}
    )

@router.post("/login/", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == email).first()

    if not user or not user.verify_password(password) or not user.active or user.role == models.UserRole.USER:
        return templates.TemplateResponse("login.html", {"request": request, "message": "Invalid credentials"})

    services = db.query(models.Services).all()
    request.session["user_id"] = user.id
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "message": f"Welcome {user.username}!", "services": services}
    )

@router.post(
    "/api/token/",
    summary="User login to get access and refresh tokens",
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "user": {
                            "id": 1,
                            "username": "john_doe",
                            "email": "john@example.com",
                            "name": "John",
                            "surname": "Doe",
                            "city": "New York",
                            "description": "Software developer"
                        }
                    }
                }
            }
        },
        400: {"description": "Email and password required"},
        401: {"description": "User not found, account not active, or invalid credentials"}
    }
)
async def api_login(request: Request, db: Session = Depends(get_db), service: Services = Depends(verify_service_or_mobile)):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    user = db.query(models.User).filter(models.User.email == email).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.active:
        raise HTTPException(status_code=401, detail="Account not active, verify your email")

    if not user.verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"user_id": user.id, "username": user.username, "email": user.email})
    refresh_token = create_refresh_token({"user_id": user.id, "username": user.username})

    return {
        "access": access_token,
        "refresh": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "name": user.name,
            "surname": user.surname,
            "city": user.city,
            "description": user.description
        }
    }

@router.post(
    "/api/token/refresh/",
    summary="Refresh access token using refresh token",
    responses={
        200: {
            "description": "Access token refreshed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                    }
                }
            }
        },
        400: {"description": "Invalid refresh token"},
        404: {"description": "User not found"}
    }
)
async def refresh(request: Request, db: Session = Depends(get_db), service: Services = Depends(verify_service_or_mobile)):
    data = await request.json()
    refresh = data.get("refresh")
    payload = verify_token(refresh)

    if payload.get("type") != "refresh":
        raise HTTPException(400, "Invalid refresh token")

    user = db.query(models.User).filter(models.User.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    new_access_token = create_access_token({
        "user_id": user.id,
        "username": user.username,
        "email": user.email
    })

    return {"access": new_access_token}

@router.post(
    "/api/google-login/",
    summary="Login or register using Google OAuth",
    responses={
        200: {
            "description": "Google login successful",
            "content": {
                "application/json": {
                    "example": {
                        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "user": {
                            "id": 1,
                            "username": "john_doe",
                            "email": "john@example.com",
                            "name": "John",
                            "surname": "Doe",
                            "city": None,
                            "description": None
                        }
                    }
                }
            }
        },
        400: {"description": "Email not provided by Google"},
        401: {"description": "Invalid token issuer or account is deactivated"},
        500: {"description": "Google OAuth not configured or authentication error"}
    }
)


async def google_login(
    data: GoogleLoginRequest,
    db: Session = Depends(get_db), 
    service: Services = Depends(verify_service_or_mobile)
):
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        
        GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        GOOGLE_ID_TOKEN_CLOCK_SKEW_SECONDS = int(os.getenv("GOOGLE_ID_TOKEN_CLOCK_SKEW_SECONDS", "60"))


        if not GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")

        idinfo = id_token.verify_oauth2_token(
            data.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=GOOGLE_ID_TOKEN_CLOCK_SKEW_SECONDS
        )

        if idinfo["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            raise HTTPException(status_code=401, detail="Invalid token issuer")

        email = idinfo.get("email")
        given_name = idinfo.get("given_name", "")
        family_name = idinfo.get("family_name", "")
        google_id = idinfo.get("sub")

        if not email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")

        user = db.query(models.User).filter(models.User.email == email).first()

        if not user:
            username = email.split("@")[0]
            base_username = username
            counter = 1
            while db.query(models.User).filter(models.User.username == username).first():
                username = f"{base_username}{counter}"
                counter += 1

            user = models.User(
                username=username,
                email=email,
                name=given_name,
                surname=family_name,
                active=True,
                email_verified=True,
                google_id=google_id,
                role=models.UserRole.USER
            )

            user.set_password(secrets.token_urlsafe(32))
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            if not user.google_id:
                user.google_id = google_id
                db.commit()

            if not user.active:
                raise HTTPException(status_code=401, detail="Account is deactivated")

        access_token = create_access_token({
            "user_id": user.id,
            "username": user.username,
            "email": user.email
        })
        refresh_token = create_refresh_token({
            "user_id": user.id,
            "username": user.username
        })

        return {
            "access": access_token,
            "refresh": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "name": user.name,
                "surname": user.surname,
                "city": user.city,
                "description": user.description
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

@router.post(
    "/api/apple-login/",
    summary="Login or register using Apple OAuth",
    responses={
        200: {"description": "Apple login successful"},
        400: {"description": "Email not provided by Apple"},
        401: {"description": "Invalid token issuer or account is deactivated"},
        500: {"description": "Apple OAuth not configured or authentication error"}
    },
)
async def apple_login(
    data: AppleLoginRequest,
    db: Session = Depends(get_db),
    service: Services = Depends(verify_service_or_mobile)
):
    try:
        payload = verify_apple_identity_token(data.identity_token)
        
        apple_id = payload.get("sub")
        token_email = payload.get("email")
        email = data.email or token_email
        
        given_name = data.given_name or ""
        family_name = data.family_name or ""
        
        if not apple_id:
            raise HTTPException(status_code=401, detail="Invalid Apple token: subject (sub) claim missing")
        
        user = db.query(models.User).filter(models.User.apple_id == apple_id).first()
        
        if not user and email:
            user = db.query(models.User).filter(models.User.email == email).first()
            
        if not user:
            if not email:
                raise HTTPException(status_code=400, detail="Email not provided by Apple")
            
            username = _generate_unique_username(db, email)
            
            user = models.User(
                username=username,
                email=email,
                name=given_name,
                surname=family_name,
                active=True,
                email_verified=True,
                apple_id=apple_id,
                role=models.UserRole.USER
            )
            
            user.set_password(secrets.token_urlsafe(32))
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            if not user.apple_id:
                user.apple_id = apple_id
                
            if not user.email_verified:
                user.email_verified = True
                
            if not user.active:
                raise HTTPException(status_code=401, detail="Account is deactivated")
            
            if given_name and not user.name:
                user.name = given_name
                
            if family_name and not user.surname:
                user.surname = family_name
                
            db.commit()
            db.refresh(user)
            
        access_token = create_access_token({
            "user_id": user.id,
            "username": user.username,
            "email": user.email
        })
        
        refresh_token = create_refresh_token({
            "user_id": user.id,
            "username": user.username
        })
        
        return {
            "access": access_token,
            "refresh": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "name": user.name,
                "surname": user.surname,
                "city": user.city,
                "description": user.description
            }
        }
        
    except HTTPException as he:
        print(f"Apple login HTTP error: {he.status_code} - {he.detail}", flush=True)
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Apple login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")


@router.post(
    "/api/verify/",
    summary="Verify access token and get user details",
    responses={
        200: {
            "description": "Token verified successfully",
            "content": {
                "application/json": {
                    "example": {
                        "user_id": 1,
                        "username": "john_doe",
                        "email": "john@example.com",
                        "type": "access",
                        "id": 1,
                        "name": "John",
                        "surname": "Doe",
                        "city": "New York",
                        "description": "Software developer",
                        "valid": True
                    }
                }
            }
        },
        401: {"description": "Invalid token"},
        404: {"description": "User not found"}
    }
)
async def api_verify(
    token: str = Form(...),
    service: models.Services = Depends(verify_service_or_mobile),
    db: Session = Depends(get_db)
):

    payload = verify_token(token, required_type="access")
    if payload is None:
        return {"valid": False, "status": 401}

    user = db.query(models.User).filter(models.User.id == payload["user_id"]).first()
    if not user:
        return {"valid": False, "status": 404}

    payload.update({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": user.name,
        "surname": user.surname,
        "city": user.city,
        "description": user.description,
        "valid": True
    })

    return JSONResponse(content=payload, media_type="application/json")

@router.post(
    "/api_register/",
    summary="Register a new user account",
    responses={
        201: {
            "description": "Account created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Account created successfully. Please verify your email."
                    }
                }
            }
        },
        202: {"description": "Account already created and waiting for email verification."},
        400: {"description": "Email or username already in use, or email already verified"},
        500: {"description": "Email sending failed"}
    }
)
async def api_register(
    data: UserRegister,
    service: models.Services = Depends(verify_service_or_mobile),
    db: Session = Depends(get_db)
):
    existing = db.query(models.User).filter(
        (models.User.email == data.email) |
        (models.User.username == data.username)
    ).first()

    if existing and existing.active:
        raise HTTPException(status_code=400, detail="Email or username already in use")

    if existing and existing.email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    now = datetime.utcnow()
    email_verification_token = secrets.token_urlsafe(32)
    email_verification_expires = _new_verification_expiry(now)

    if existing and not existing.active:
        
        if _verification_is_pending(existing, now):
            return JSONResponse(
                status_code = 202,
                content = {"message": "Account already exists but not verified. Please check your email for the verification link.", "verification_pending": True}
            )
            
        previous_token = existing.email_verification_token
        previous_expires = existing.email_verification_expires
        
        existing.email_verification_token = email_verification_token
        existing.email_verification_expires = email_verification_expires
        db.commit()

        email_sent = send_verification_email(
            email=data.email,
            token=email_verification_token,
            username=data.username
        )

        if not email_sent:
            existing.email_verification_token = previous_token
            existing.email_verification_expires = previous_expires
            db.commit()
            raise HTTPException(status_code=500, detail="Email sending failed")

        return JSONResponse(
            status_code=201,
            content={"message": "Account created successfully. Please verify your email."}
        )

    user = models.User(
        username=data.username,
        email=data.email,
        name=data.firstName,
        surname=data.lastName,
        city=data.city,
        description=data.description,
        active=False,
        email_verified=False,
        email_verification_token=email_verification_token,
        email_verification_expires=email_verification_expires
    )

    user.set_password(data.password)
    db.add(user)
    db.commit()
    db.refresh(user)

    email_sent = send_verification_email(
        email=data.email,
        token=email_verification_token,
        username=data.username
    )

    if not email_sent:
        db.delete(user)
        db.commit()
        raise HTTPException(status_code=500, detail="Email sending failed")

    return JSONResponse(
        status_code=201,
        content={"message": "Account created successfully. Please verify your email."}
    )

@router.get("/verify-email")
async def verify_email(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(
        models.User.email_verification_token == token
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")

    if user.email_verification_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Verification token expired")

    user.email_verified = True
    user.active = True
    user.email_verification_token = None
    user.email_verification_expires = None
    db.commit()

    return templates.TemplateResponse(
        "success.html",
        {"request": request, "message": "Email verified successfully!", "type": "Email"}
    )

@router.post(
    "/resend-verification/",
    summary="Resend email verification link",
    responses={
        200: {
            "description": "Verification email sent successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Verification email sent again"
                    }
                }
            }
        },
        400: {"description": "Email already verified"},
        404: {"description": "Email not found"},
        429: {"description": "Too many requests. Retry later"},
        500: {"description": "Email sending failed"}
    }
)
async def resend_verification(
    request: Request,
    db: Session = Depends(get_db),
    service: models.Services = Depends(verify_service_or_mobile),
):
    data = await request.json()
    email = data.get("email")

    user = db.query(models.User).filter(models.User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    if user.email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    # token = secrets.token_urlsafe(32)
    # expires = datetime.utcnow() + timedelta(hours=24)
    
    now = datetime.utcnow()
    seconds_left = _seconds_until_resent_allowed(user, now)
    if seconds_left > 0:
        raise HTTPException(
            status_code=429, 
            detail=f"Too many requests. Please wait {seconds_left} seconds before requesting a new verification email.",
            headers={"Retry-After": str(seconds_left)}
        )
        
    previous_token = user.email_verification_token
    previous_expires = user.email_verification_expires
    
    token = secrets.token_urlsafe(32)
    expires = _new_verification_expiry(now)

    user.email_verification_token = token
    user.email_verification_expires = expires
    db.commit()

    email_sent = send_verification_email(
        email=user.email,
        token=token,
        username=user.username
    )

    if not email_sent:
        user.email_verification_token = previous_token
        user.email_verification_expires = previous_expires
        db.commit()
        raise HTTPException(status_code=500, detail="Email sending failed")

    return {"message": "Verification email sent again"}

@router.post(
    "/reset-password/",
    summary="Request password reset email",
    responses={
        200: {
            "description": "Password reset email sent successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Password reset email sent"
                    }
                }
            }
        },
        404: {"description": "Email not found"},
        500: {"description": "Email sending failed"}
    }
)
async def request_reset_password(
    request: Request,
    db: Session = Depends(get_db),
    service: models.Services = Depends(verify_service_or_mobile),
):
    data = await request.json()
    email = data.get("email")

    user = db.query(models.User).filter(models.User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=24)

    user.password_reset_token = token
    user.password_reset_expires = expires
    db.commit()

    email_sent = send_forgot_password(
        email=user.email,
        token=token,
        username=user.username
    )

    if not email_sent:
        user.password_reset_token = None
        user.password_reset_expires = None
        db.commit()
        raise HTTPException(status_code=500, detail="Email sending failed")

    return {"message": "Password reset email sent"}

@router.get("/reset-password/")
def get_reset_form(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(
        models.User.password_reset_token == token
    ).first()

    if not user or user.password_reset_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    return templates.TemplateResponse(
        "reset_password.html",
        {"request": request, "token": token}
    )

@router.post("/verify-reset-password/")
def verify_reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Passwords do not match", "type": "Password"},
            status_code=400
        )

    user = db.query(models.User).filter(
        models.User.password_reset_token == token
    ).first()

    if not user or user.password_reset_expires < datetime.utcnow():
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Invalid or expired token", "type": "Token"},
            status_code=400
        )

    user.set_password(password)
    user.password_reset_token = None
    user.password_reset_expires = None
    db.commit()

    return templates.TemplateResponse(
        "success.html",
        {"request": request, "message": "Password successfully updated!", "type": "Password"}
    )