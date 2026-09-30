"""
Servio backend settings.

Bütün sirlər (SECRET_KEY, DB parolu və s.) `.env` faylından oxunur —
`.env.example`-ə bax. `.env` heç vaxt git-ə commit edilməməlidir (.gitignore-da var).
"""
import environ
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DB_ENGINE=(str, "mssql"),
)
# .env faylı repo kökündə axtarılır — production-da adətən .env yoxdur,
# dəyərlər birbaşa server/konteynerin mühit dəyişənlərindən gəlir.
environ.Env.read_env(BASE_DIR / ".env")

# --- Təhlükəsizlik əsasları ---
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-dev-key-DEYISDIR-PRODUCTIONDA")
DEBUG = env("DJANGO_DEBUG")

if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError(
        "DJANGO_SECRET_KEY .env-də təyin edilməyib — production-da (DEBUG=0) "
        "defolt açarla işə düşmək qəti qadağandır. `.env` faylına unikal "
        "DJANGO_SECRET_KEY əlavə edin (məs. `python3 -c \"import secrets; "
        "print(secrets.token_urlsafe(50))\"` ilə yaradın)."
    )

ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS") or (["*"] if DEBUG else [])

INSTALLED_APPS = [
    "jazzmin",  # django.contrib.admin-dən ƏVVƏL olmalıdır

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",

    "tenants",
    "accounts",
    "customers",
    "repairs",
    "inventory",
    "marketplace",
    "finance",
    "suppliers",
    "platform_admin",
    "reports",
    "sitecontent",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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

# --- Verilənlər bazası ---
# DB_ENGINE=mssql (defolt, production) və ya DB_ENGINE=sqlite (yalnız yerli/test mühit üçün).
if env("DB_ENGINE") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "mssql",
            "NAME": env("MSSQL_DATABASE", default="servio"),
            "USER": env("MSSQL_USER", default="sa"),
            "PASSWORD": env("MSSQL_PASSWORD", default=""),
            "HOST": env("MSSQL_HOST", default="localhost"),
            "PORT": env("MSSQL_PORT", default="1433"),
            "OPTIONS": {
                # Server-də quraşdırılmış ODBC Driver-in adı ilə eyni olmalıdır
                # (Ubuntu/Debian-da: "ODBC Driver 18 for SQL Server").
                "driver": env("MSSQL_DRIVER", default="ODBC Driver 18 for SQL Server"),
                "extra_params": env("MSSQL_EXTRA_PARAMS", default="Encrypt=yes;TrustServerCertificate=yes;"),
            },
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "az"
TIME_ZONE = "Asia/Baku"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF / JWT ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "config.pagination.FlexiblePageNumberPagination",
    "PAGE_SIZE": 20,
    # Giriş (login) sorğularına sürət limiti — şifrə güc-sınama (brute-force) hücumlarına qarşı.
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "anon": "120/min",
    },
}
if not DEBUG:
    # Production-da DRF-in "Browsable API" HTML formu söndürülür — sadəcə JSON.
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = ("rest_framework.renderers.JSONRenderer",)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --- CORS / CSRF ---
# .env-də CORS_ALLOWED_ORIGINS/CSRF_TRUSTED_ORIGINS verilməsə, dev rejimində
# yalnız yerli Next.js server-inə icazə verilir (production-da boş qalır,
# yəni .env-də mütləq real domen göstərilməlidir).
_default_dev_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS") or (_default_dev_origins if DEBUG else [])
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS") or (_default_dev_origins if DEBUG else [])

# --- Production təhlükəsizlik başlıqları ---
# DEBUG=0 olanda avtomatik aktivləşir; yerli inkişafda (DEBUG=1) bu
# yoxlamalar HTTP üzərindən test etməyə mane olmasın deyə söndürülür.
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    # Nginx/Cloudflare kimi tərs-proksi arxasında işləyirsə, proksinin
    # göndərdiyi başlığa etibar edərək HTTPS-i düzgün aşkarlamaq üçün:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Jazzmin (admin panel dizaynı) ---
from .jazzmin_conf import JAZZMIN_SETTINGS, JAZZMIN_UI_TWEAKS  # noqa: E402,F401
