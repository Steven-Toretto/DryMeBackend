"""
Django settings for laundry_backend project.
"""

from pathlib import Path
from datetime import timedelta
import os
import dj_database_url
import cloudinary
from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured

RENDER = os.environ.get("RENDER", False)

# ===============================
# BASE DIR
# ===============================
BASE_DIR = Path(__file__).resolve().parent.parent

# ===============================
# SECURITY
# ===============================
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-xns&xq^j5-y8b=$2p!e+u*h0s0gqqyi7gxxyeo2*vr3)lb4iy8"
)

# DEBUG = True
DEBUG = not bool(RENDER)

ALLOWED_HOSTS = [
    "drymebackend-2.onrender.com",
    "localhost",
    "127.0.0.1",
]

# ===============================
# INSTALLED APPS
# ===============================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",

    # cloudinary
    "cloudinary",
    "cloudinary_storage",

    # local apps
    "dryMe",
]

# site admin
AUTHENTICATION_BACKENDS = [
    'dryMe.backends.EmailBackend',
]

# ===============================
# MIDDLEWARE
# ===============================
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ===============================
# CORS
# ===============================
CORS_ALLOWED_ORIGINS = [
    "https://dry-me-frontend.vercel.app",
    "http://localhost:5173",
]

CORS_ALLOW_ALL_ORIGINS = False

# ===============================
# CSRF
# ===============================
CSRF_TRUSTED_ORIGINS = [
    "https://dry-me-frontend.vercel.app",
]

# ===============================
# PROXY SSL
# ===============================
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# ===============================
# URLS
# ===============================
ROOT_URLCONF = "laundry_backend.urls"

# ===============================
# TEMPLATES
# ===============================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",

                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ===============================
# WSGI
# ===============================
WSGI_APPLICATION = "laundry_backend.wsgi.application"

# ===============================
# DATABASE
# ===============================

if RENDER:
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            ssl_require=True
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ===============================
# PASSWORD VALIDATION
# ===============================
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ===============================
# CUSTOM USER MODEL
# ===============================
AUTH_USER_MODEL = "dryMe.User"

# ===============================
# DJANGO REST FRAMEWORK
# ===============================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),

    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),

    # ✅ Pagination — prevents large queries from crashing the server
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}

# ===============================
# 💳 MPESA
# ===============================
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "174379")
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY", "")

# Unguessable token in the callback path. Generate with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
MPESA_CALLBACK_SECRET = os.environ.get("MPESA_CALLBACK_SECRET", "")
if RENDER and not MPESA_CALLBACK_SECRET:
    raise ImproperlyConfigured("MPESA_CALLBACK_SECRET must be set in production.")

# The URL Safaricom calls MUST include the secret.
MPESA_CALLBACK_URL = os.environ.get(
    "MPESA_CALLBACK_URL",
    f"https://drymebackend-2.onrender.com/api/mpesa/callback/{MPESA_CALLBACK_SECRET}/",
)

# Optional extra layer. Comma-separated Safaricom source IPs (take them from the
# current Daraja docs). Empty = disabled. Verify your host's X-Forwarded-For
# chain before enabling, or you'll lock out real callbacks.
MPESA_CALLBACK_ALLOWED_IPS = [
    ip.strip() for ip in os.environ.get("MPESA_CALLBACK_ALLOWED_IPS", "").split(",") if ip.strip()
]

# ===============================
# 💰 WALLET / PAYOUTS
# ===============================
def _env_decimal(name, default):
    raw = os.environ.get(name)
    if raw is None:
        if RENDER:  # fail loudly in production rather than silently paying out at a 0 fee
            raise ImproperlyConfigured(f"{name} must be set in production.")
        raw = default
    return Decimal(raw)

COMMISSION_RATE = _env_decimal("COMMISSION_RATE", "0.10")          # 0.10 = 10%
PAYOUT_FEES = {
    "mpesa": _env_decimal("MPESA_PAYOUT_FEE", "0"),                # whole KES, from your Daraja B2C tariff
    "bank": _env_decimal("BANK_PAYOUT_FEE", "0"),
}
PAYOUT_MIN_NET = Decimal("1")  # smallest amount the owner must actually receive

if not Decimal("0") <= COMMISSION_RATE < Decimal("1"):
    raise ImproperlyConfigured("COMMISSION_RATE must be between 0 and 1.")
if PAYOUT_FEES["mpesa"] != PAYOUT_FEES["mpesa"].to_integral_value():
    raise ImproperlyConfigured("MPESA_PAYOUT_FEE must be a whole number of shillings.")

# Seconds to wait before another STK prompt can be sent for the same order while
# one is still pending. Set to 0 to disable. Safe either way — every prompt is
# tracked as its own PaymentAttempt — this just stops accidental double prompts.
MPESA_STK_COOLDOWN_SECONDS = int(os.environ.get("MPESA_STK_COOLDOWN_SECONDS", "60"))

MPESA_BASE_URL = os.environ.get("MPESA_BASE_URL", "https://sandbox.safaricom.co.ke")


# ===============================
# JWT
# ===============================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ===============================
# CLOUDINARY CONFIG
# ===============================

if RENDER:

    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    )

    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME"),
        "API_KEY": os.environ.get("CLOUDINARY_API_KEY"),
        "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET"),
    }

    # Django 4.2+ uses STORAGES dict — DEFAULT_FILE_STORAGE is ignored
    STORAGES = {
        "default": {
            "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# ===============================
# MEDIA FILES
# ===============================
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ===============================
# STATIC FILES
# ===============================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# STATICFILES_STORAGE is now handled inside the STORAGES dict above (Django 4.2+)

# ===============================
# INTERNATIONALIZATION
# ===============================
LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True
USE_TZ = True

# ===============================
# DEFAULT PRIMARY KEY
# ===============================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

import sys
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]