from pathlib import Path
import os
import dotenv
from django.urls import re_path
from django.views.static import serve
from django.conf import settings
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.templatetags.static import static


dotenv.load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SITE_ID = int(os.getenv('SITE_ID'))
LOGIN_REDIRECT_URL = '/admin/' if os.getenv('FORCE_SCRIPT_NAME') == "/" else os.getenv('FORCE_SCRIPT_NAME') + '/admin/'
LOGOUT_REDIRECT_URL = os.getenv('FORCE_SCRIPT_NAME')

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 465  # porta SSL, altrimenti 587
EMAIL_USE_TLS = False
EMAIL_USE_SSL = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

SECRET_KEY = os.environ.get('SECRET_KEY')

DEBUG = False
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = ['https://xrtourguide.di.unisa.it']
CORS_ORIGIN_ALLOW = True

SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "web",
    "xr_tour_guide_unisa",
    "xrtourguide.di.unisa.it"
]

FORCE_SCRIPT_NAME = os.getenv('FORCE_SCRIPT_NAME')
STATIC_URL = "/static/" if os.getenv('FORCE_SCRIPT_NAME') == "/" else os.getenv('FORCE_SCRIPT_NAME') + '/static/'
MEDIA_URL = "/media/" if os.getenv('FORCE_SCRIPT_NAME') == "/" else os.getenv('FORCE_SCRIPT_NAME') + '/media/'

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

INSTALLED_APPS = [
    "unfold",  # before django.contrib.admin
    "unfold.contrib.filters",  # optional, if special filters are needed
    "unfold.contrib.forms",  # optional, if special form elements are needed
    "unfold.contrib.inlines",  # optional, if special inlines are needed
    "unfold.contrib.import_export",  # optional, if django-import-export package is used
    "unfold.contrib.guardian",  # optional, if django-guardian package is used
    "unfold.contrib.simple_history",
    'rest_framework',
    'rest_framework.authtoken',
    'drf_yasg',
    'location_field.apps.DefaultConfig',
    "storages",
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'nested_admin',
    'django_celery_beat',
    'xr_tour_guide_core',
    'xr_tour_guide_public',
    'django.contrib.sites',
    'corsheaders',
]


AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    # 'allauth.account.auth_backends.AuthenticationBackend',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # 'allauth.account.middleware.AccountMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "https://accounts.google.com",
]
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Permetti richieste da Google
CSRF_TRUSTED_ORIGINS = [
    'http://localhost',
    'http://127.0.0.1',
]
# SOCIALACCOUNT_LOGIN_ON_GET = True
# SOCIALACCOUNT_AUTO_SIGNUP = True
# SOCIALACCOUNT_ADAPTER = 'xr_tour_guide_core.accounts.adapters.CustomSocialAccountAdapter'

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
    "redis": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv('CELERY_BROKER_URL'),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

AUTH_USER_MODEL = 'xr_tour_guide_core.CustomUser'

ROOT_URLCONF = 'xr_tour_guide.urls'
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760 * 10  # 10 GB

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        # 'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

LOCATION_FIELD = {
    'map.provider': 'openstreetmap',
    'search.provider': 'nominatim',
}

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
    }
}

DEBUG = False

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.template': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'xr_tour_guide.context_processors.script_name',
            ],
        },
    },
]

WSGI_APPLICATION = 'xr_tour_guide.wsgi.application'

# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
AWS_ACCESS_KEY_ID = os.getenv("MINIO_ROOT_USER")
AWS_SECRET_ACCESS_KEY = os.getenv("MINIO_ROOT_PASSWORD")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL")
AWS_S3_FILE_OVERWRITE = False
AWS_S3_USE_SSL = False
AWS_DEFAULT_ACL = None
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=604800',
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en'
LANGUAGES = [
    ('en', 'English'),
    ('it', 'Italiano'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

UNFOLD = {
    "SITE_TITLE": "XRTourGuide",
    "SITE_HEADER": "XRTourGuide",
    # "SITE_TAGLINE": "Gestione contenuti",
    "SITE_LOGO": "/static/admin/img/XRTOURGUIDE.png",
    "SHOW_VIEW_ON_SITE": False,
    "DASHBOARD_CALLBACK": "xr_tour_guide.views.dashboard_callback",
    "STYLES": [
        lambda request: static("unfold/css/styles.css"),
        lambda request: static("admin/css/xrtourguide-brand.css"),
    ],
    
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": lambda request: request.user.is_superuser,
        "navigation": [
            {
                "separator": False,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": _("Functionalities"),
                "separator": False,
                "collapsible": True,
                "default_open": True,
                "items": [
                    {
                        "title": _("Tour"),
                        "icon": "map",
                        "link": reverse_lazy("admin:xr_tour_guide_core_tour_changelist"),
                    },
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:xr_tour_guide_core_customuser_changelist"),
                    },
                    {
                        "title": _("Reviews"),
                        "icon": "message",
                        "link": reverse_lazy("admin:xr_tour_guide_core_review_changelist"),
                    }
                ],
            },
        ],
    }
}