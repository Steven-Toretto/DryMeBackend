"""
Django settings for laundry_backend project.
"""

from pathlib import Path
from datetime import timedelta
import os
import dj_database_url
import cloudinary
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
}

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

    DEFAULT_FILE_STORAGE = (
        "cloudinary_storage.storage.MediaCloudinaryStorage"
    )

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

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

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



# """
# Django settings for laundry_backend project.
# """

# from pathlib import Path
# from datetime import timedelta
# import os
# import dj_database_url

# # ===============================
# # BASE DIR
# # ===============================
# BASE_DIR = Path(__file__).resolve().parent.parent

# # ===============================
# # SECURITY
# # ===============================
# SECRET_KEY = os.environ.get(
#     "SECRET_KEY",
#     "django-insecure-xns&xq^j5-y8b=$2p!e+u*h0s0gqqyi7gxxyeo2*vr3)lb4iy8"
# )

# DEBUG = False

# ALLOWED_HOSTS = [
#     "drymebackend-2.onrender.com",
#     "localhost",
#     "127.0.0.1",
# ]

# # ===============================
# # INSTALLED APPS
# # ===============================
# INSTALLED_APPS = [
#     "django.contrib.admin",
#     "django.contrib.auth",
#     "django.contrib.contenttypes",
#     "django.contrib.sessions",
#     "django.contrib.messages",
#     "django.contrib.staticfiles",

#     # third party
#     "rest_framework",
#     "rest_framework_simplejwt",
#     "corsheaders",

#     'cloudinary',
#     'cloudinary_storage',

#     # local apps
#     "dryMe",
# ]

# # ===============================
# # MIDDLEWARE
# # ===============================
# MIDDLEWARE = [
#     "corsheaders.middleware.CorsMiddleware",

#     "django.middleware.security.SecurityMiddleware",
#     "whitenoise.middleware.WhiteNoiseMiddleware",

#     "django.contrib.sessions.middleware.SessionMiddleware",
#     "django.middleware.common.CommonMiddleware",

#     "django.middleware.csrf.CsrfViewMiddleware",
#     "django.contrib.auth.middleware.AuthenticationMiddleware",
#     "django.contrib.messages.middleware.MessageMiddleware",

#     "django.middleware.clickjacking.XFrameOptionsMiddleware",
# ]

# # ===============================
# # CORS
# # ===============================
# CORS_ALLOWED_ORIGINS = [
#     "https://dry-me-frontend.vercel.app",
#     "http://localhost:5173",
# ]

# CORS_ALLOW_ALL_ORIGINS = False

# # ===============================
# # CSRF
# # ===============================
# CSRF_TRUSTED_ORIGINS = [
#     "https://dry-me-frontend.vercel.app",
# ]

# # ===============================
# # PROXY SSL
# # ===============================
# SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# USE_X_FORWARDED_HOST = True

# # ===============================
# # URLS
# # ===============================
# ROOT_URLCONF = "laundry_backend.urls"

# # ===============================
# # TEMPLATES
# # ===============================
# TEMPLATES = [
#     {
#         "BACKEND": "django.template.backends.django.DjangoTemplates",
#         "DIRS": [],
#         "APP_DIRS": True,
#         "OPTIONS": {
#             "context_processors": [
#                 "django.template.context_processors.debug",
#                 "django.template.context_processors.request",

#                 "django.contrib.auth.context_processors.auth",
#                 "django.contrib.messages.context_processors.messages",
#             ],
#         },
#     },
# ]

# # ===============================
# # WSGI
# # ===============================
# WSGI_APPLICATION = "laundry_backend.wsgi.application"

# # ===============================
# # DATABASE
# # ===============================

# DATABASES = {
#     "default": dj_database_url.config(
#         default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
#     )
# }

# # DATABASES = {
# #     "default": dj_database_url.config(
# #         default=os.environ.get("DATABASE_URL")
# #     )
# # }

# # ===============================
# # PASSWORD VALIDATION
# # ===============================
# AUTH_PASSWORD_VALIDATORS = [
#     {
#         "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
#     },
#     {
#         "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
#     },
#     {
#         "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
#     },
#     {
#         "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
#     },
# ]

# # ===============================
# # CUSTOM USER MODEL
# # ===============================
# AUTH_USER_MODEL = "dryMe.User"

# # ===============================
# # DJANGO REST FRAMEWORK
# # ===============================
# REST_FRAMEWORK = {
#     "DEFAULT_AUTHENTICATION_CLASSES": (
#         "rest_framework_simplejwt.authentication.JWTAuthentication",
#     ),

#     "DEFAULT_PERMISSION_CLASSES": (
#         "rest_framework.permissions.IsAuthenticated",
#     ),
# }

# # ===============================
# # JWT
# # ===============================
# SIMPLE_JWT = {
#     "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
#     "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
#     "AUTH_HEADER_TYPES": ("Bearer",),
# }

# # ===============================
# # MEDIA FILES
# # ===============================
# MEDIA_URL = "/media/"
# MEDIA_ROOT = BASE_DIR / "media"

# # 
# CLOUDINARY_STORAGE = {
#     'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
#     'API_KEY': os.environ.get('CLOUDINARY_API_KEY'),
#     'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
# }

# # ===============================
# # STATIC FILES
# # ===============================
# STATIC_URL = "/static/"
# STATIC_ROOT = BASE_DIR / "staticfiles"

# STATICFILES_STORAGE = (
#     "whitenoise.storage.CompressedManifestStaticFilesStorage"
# )

# # ===============================
# # DEFAULT FILE STORAGE
# # ===============================

# DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
# # DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# # ===============================
# # INTERNATIONALIZATION
# # ===============================
# LANGUAGE_CODE = "en-us"

# TIME_ZONE = "UTC"

# USE_I18N = True
# USE_TZ = True

# # ===============================
# # DEFAULT PRIMARY KEY
# # ===============================
# DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField" 









