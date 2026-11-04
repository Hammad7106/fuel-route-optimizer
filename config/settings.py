"""Django settings for the fuel route optimizer.

All environment-specific values are read from environment variables
(or a local `.env` file) via django-environ.
"""

from pathlib import Path

import environ
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    OSRM_BASE_URL=(str, "https://router.project-osrm.org"),
    ROUTING_TIMEOUT_SECONDS=(float, 10.0),
    VEHICLE_MAX_RANGE_MILES=(float, 500.0),
    VEHICLE_MPG=(float, 10.0),
    ROUTE_CACHE_TIMEOUT=(int, 60 * 60 * 24),
    STATION_SEARCH_RADIUS_MILES=(float, 10.0),
    FUEL_STOP_MERGE_MILES=(float, 25.0),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")


# Application definition

INSTALLED_APPS = [
    # Unfold must come before django.contrib.admin so its templates win.
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "drf_spectacular",
    # Local
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves static files (the admin's CSS/JS) when DEBUG is off, as in Docker.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}


# Cache: route results are cached so repeat queries skip the routing API.
# It must be shared by all gunicorn workers, or a repeat trip (or the map
# page) landing on another worker calls the API again. The default file cache
# is shared within one container; use e.g. rediscache://redis:6379/0 to share
# it across containers.

CACHES = {
    "default": env.cache_url("CACHE_URL", default=f"filecache://{BASE_DIR / '.cache' / 'django'}"),
}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "routing.errors.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


SPECTACULAR_SETTINGS = {
    "TITLE": "Fuel Route Optimizer API",
    "DESCRIPTION": (
        "Plans the cheapest fuel stops for a drive between two US locations, "
        "for a vehicle with a 500-mile range at 10 MPG.\n\n"
        "Locations are `\"City, ST\"` (e.g. `\"Dallas, TX\"`) or `\"lat,lng\"`. "
        "Each new trip makes one routing API call; repeat trips are served from cache.\n\n"
        "The same plan on a map: `GET /api/route/map/?start=Dallas, TX&finish=Denver, CO`."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Pinned so a new Swagger UI release can't change the docs page unexpectedly.
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.1",
    "SWAGGER_UI_FAVICON_HREF": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.1/favicon-32x32.png",
    # Show how long each "Try it out" request took (cached vs new trips).
    "SWAGGER_UI_SETTINGS": {"displayRequestDuration": True},
}


# Admin (django-unfold)

UNFOLD = {
    "SITE_TITLE": "Fuel Route Optimizer",
    "SITE_HEADER": "Fuel Route Optimizer",
    "SITE_SUBHEADER": "Admin",
    "SITE_SYMBOL": "local_gas_station",
    "SITE_URL": "/",
    "LOGIN": {
        # Illustration shown beside the login form on wide screens.
        "image": lambda request: static("routing/admin-login.svg"),
    },
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Fuel data",
                "items": [
                    {
                        "title": "Fuel stations",
                        "icon": "local_gas_station",
                        "link": reverse_lazy("admin:routing_fuelstation_changelist"),
                    },
                ],
            },
            {
                "title": "API",
                "separator": True,
                "items": [
                    {"title": "API docs (Swagger)", "icon": "api", "link": "/api/docs/"},
                    {
                        "title": "Example map",
                        "icon": "map",
                        "link": "/api/route/map/?start=Dallas, TX&finish=Denver, CO",
                    },
                    {"title": "Health", "icon": "monitor_heart", "link": "/api/health/"},
                ],
            },
            {
                "title": "Users",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": "Groups",
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
}


# Logging

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


# Fuel route optimizer

OSRM_BASE_URL = env("OSRM_BASE_URL")
ROUTING_TIMEOUT_SECONDS = env("ROUTING_TIMEOUT_SECONDS")
FUEL_PRICES_CSV = BASE_DIR / "data" / "fuel_prices.csv"
US_PLACES_FILE = BASE_DIR / "data" / "us_places.csv.gz"
VEHICLE_MAX_RANGE_MILES = env("VEHICLE_MAX_RANGE_MILES")
VEHICLE_MPG = env("VEHICLE_MPG")
ROUTE_CACHE_TIMEOUT = env("ROUTE_CACHE_TIMEOUT")
STATION_SEARCH_RADIUS_MILES = env("STATION_SEARCH_RADIUS_MILES")
FUEL_STOP_MERGE_MILES = env("FUEL_STOP_MERGE_MILES")
