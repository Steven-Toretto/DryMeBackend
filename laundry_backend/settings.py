"""
Django settings for laundry_backend project.
"""

from pathlib import Path
from datetime import timedelta
import os
import dj_database_url

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

DEBUG = False

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

    'cloudinary',
    'cloudinary_storage',

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
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL")
    )
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
# MEDIA FILES
# ===============================
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# 
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
}

# ===============================
# STATIC FILES
# ===============================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# ===============================
# DEFAULT FILE STORAGE
# ===============================

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
# DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

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

# # 
# import dj_database_url

# # Build paths inside the project like this: BASE_DIR / 'subdir'.
# BASE_DIR = Path(__file__).resolve().parent.parent

# # SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY = 'django-insecure-xns&xq^j5-y8b=$2p!e+u*h0s0gqqyi7gxxyeo2*vr3)lb4iy8'

# # SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = False

# ALLOWED_HOSTS = [
#     "drymebackend-2.onrender.com",
#     "localhost",
#     "127.0.0.1",
# ]

# # Application definition
# INSTALLED_APPS = [
#     'django.contrib.admin',
#     'django.contrib.auth',
#     'django.contrib.contenttypes',
#     'django.contrib.sessions',
#     'django.contrib.messages',
#     'django.contrib.staticfiles',

#     'rest_framework',
#     'corsheaders',

#     'dryMe',
# ]

# MIDDLEWARE = [
#     'corsheaders.middleware.CorsMiddleware',

#     'django.middleware.security.SecurityMiddleware',
#     'django.contrib.sessions.middleware.SessionMiddleware',
#     'django.middleware.common.CommonMiddleware',
#     'django.middleware.csrf.CsrfViewMiddleware',
#     'django.contrib.auth.middleware.AuthenticationMiddleware',
#     'django.contrib.messages.middleware.MessageMiddleware',
#     'django.middleware.clickjacking.XFrameOptionsMiddleware',
# ]

# # CORS settings
# CORS_ALLOWED_ORIGINS = [
#     "https://dry-me-frontend.vercel.app",
#     "http://localhost:5173",
# ]

# CORS_ALLOW_ALL_ORIGINS = False

# # CSRF trusted origins
# CSRF_TRUSTED_ORIGINS = [
#     "https://dry-me-frontend.vercel.app",
# ]

# # Proxy settings for secure deployment
# SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# USE_X_FORWARDED_HOST = True

# ROOT_URLCONF = 'laundry_backend.urls'

# TEMPLATES = [
#     {
#         'BACKEND': 'django.template.backends.django.DjangoTemplates',
#         'DIRS': [],
#         'APP_DIRS': True,
#         'OPTIONS': {
#             'context_processors': [
#                 'django.template.context_processors.debug',
#                 'django.template.context_processors.request',

#                 'django.contrib.auth.context_processors.auth',
#                 'django.contrib.messages.context_processors.messages',
#             ],
#         },
#     },
# ]

# WSGI_APPLICATION = 'laundry_backend.wsgi.application'

# # Database

# DATABASES = {
#     "default": dj_database_url.parse(
#         os.environ.get("DATABASE_URL")
#     )
# }

# # DATABASES = {
# #     'default': {
# #         'ENGINE': 'django.db.backends.sqlite3',
# #         'NAME': BASE_DIR / 'db.sqlite3',
# #     }
# # }

# # Password validation
# AUTH_PASSWORD_VALIDATORS = [
#     {
#         'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'
#     },
# ]

# # Custom user model
# AUTH_USER_MODEL = 'dryMe.User'

# # DRF + JWT
# REST_FRAMEWORK = {
#     'DEFAULT_AUTHENTICATION_CLASSES': (
#         'rest_framework_simplejwt.authentication.JWTAuthentication',
#     ),

#     'DEFAULT_PERMISSION_CLASSES': (
#         'rest_framework.permissions.IsAuthenticated',
#     ),
# }


# SIMPLE_JWT = {
#     "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
#     "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
#     "AUTH_HEADER_TYPES": ("Bearer",),
# }

# # SIMPLE_JWT = {
# #     'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
# #     'AUTH_HEADER_TYPES': ('Bearer',),
# # }

# # Media files
# # MEDIA_URL = '/media/'
# MEDIA_URL = 'https://drymebackend-2.onrender.com/media/'
# MEDIA_ROOT = BASE_DIR / 'media'

# # Static files
# STATIC_URL = '/static/'

# # File storage
# DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# # Internationalization
# LANGUAGE_CODE = 'en-us'

# TIME_ZONE = 'UTC'

# USE_I18N = True
# USE_TZ = True

# # Default primary key field type
# DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'