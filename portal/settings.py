"""Environment-driven settings for the portal and isolated development."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no", ""}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean")

DEBUG = env_bool("DEBUG")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY is required")
ALLOWED_HOSTS = [v.strip() for v in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if v.strip()]
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework.authtoken", "rest_framework", "blog", "users", "api",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "portal.security.ResponseSecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "portal.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": [
    "django.template.context_processors.csp", "django.template.context_processors.debug", "django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages",
]}}]
WSGI_APPLICATION = "portal.wsgi.application"
DB_ENGINE = os.environ.get("DB_ENGINE", "postgresql")
if DB_ENGINE == "sqlite":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / ".local" / "db.sqlite3"))}}
elif DB_ENGINE == "postgresql":
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.environ.get("DATABASE_NAME", ""), "USER": os.environ.get("DATABASE_USER", ""), "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""), "HOST": os.environ.get("DATABASE_HOST", ""), "PORT": os.environ.get("DATABASE_PORT", "5432"), "OPTIONS": {"sslmode": os.environ.get("DATABASE_SSLMODE", "require")}}}
else:
    raise ImproperlyConfigured("DB_ENGINE must be postgresql or sqlite")
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation." + name} for name in ["UserAttributeSimilarityValidator", "MinimumLengthValidator", "CommonPasswordValidator", "NumericPasswordValidator"]]
LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", str(BASE_DIR / ".local" / "static")))
STATICFILES_DIRS = [BASE_DIR / "static-src"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / ".local" / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@localhost")
PASSWORD_RESET_TIMEOUT = 86400
REST_FRAMEWORK = {"EXCEPTION_HANDLER": "api.helpers.utils.custom_exception_handler"}
# Preserve inherited series capacity until upload limits are validated with real workloads.
MAX_UPLOAD_FILES = os.environ.get("MAX_UPLOAD_FILES")
DATA_UPLOAD_MAX_NUMBER_FILES = int(MAX_UPLOAD_FILES) if MAX_UPLOAD_FILES else None
FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440
SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
if env_bool("TRUST_PROXY_HTTPS"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Opt-in only: credentials are server-side and never injected into templates.
MEDIA_STORAGE = os.environ.get('MEDIA_STORAGE', 'filesystem')
R2_ENDPOINT_URL = os.environ.get('R2_ENDPOINT_URL', '')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '')
R2_IMAGE_BUCKET = os.environ.get('R2_IMAGE_BUCKET', '')
R2_DICOM_BUCKET = os.environ.get('R2_DICOM_BUCKET', '')
R2_SIGNED_URL_SECONDS = int(os.environ.get('R2_SIGNED_URL_SECONDS', '300'))
# Empty preserves private signed URLs and supports configuration-only rollback.
from .media_config import validate_public_image_origin, image_csp_origins
R2_IMAGE_PUBLIC_BASE_URL = validate_public_image_origin(os.environ.get('R2_IMAGE_PUBLIC_BASE_URL', ''))
if R2_IMAGE_PUBLIC_BASE_URL and (MEDIA_STORAGE != 'r2' or not R2_IMAGE_BUCKET or not R2_DICOM_BUCKET or R2_IMAGE_BUCKET == R2_DICOM_BUCKET):
    raise ImproperlyConfigured('Public images require R2 and distinct configured image and private DICOM buckets')
if MEDIA_STORAGE == 'r2':
    STORAGES = {
        'default': {'BACKEND': 'portal.storage.PrivateImageStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
elif MEDIA_STORAGE != 'filesystem':
    raise ImproperlyConfigured('MEDIA_STORAGE must be filesystem or r2')

# Explicit upload bounds. No original DICOM is retained without opting in.
MAX_IMAGE_UPLOAD_BYTES = int(os.environ.get('MAX_IMAGE_UPLOAD_BYTES', str(32 * 1024 * 1024)))
MAX_CASE_UPLOAD_BYTES = int(os.environ.get('MAX_CASE_UPLOAD_BYTES', str(256 * 1024 * 1024)))
MAX_IMAGE_PIXELS = int(os.environ.get('MAX_IMAGE_PIXELS', '40000000'))
DICOM_RETENTION_ENABLED = env_bool('DICOM_RETENTION_ENABLED', False)
PRIVATE_DICOM_ROOT = Path(os.environ.get('PRIVATE_DICOM_ROOT', str(BASE_DIR / '.local' / 'private-dicom')))
DATABASE_SSLROOTCERT = os.environ.get('DATABASE_SSLROOTCERT', '')
if DATABASE_SSLROOTCERT and DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    DATABASES['default']['OPTIONS']['sslrootcert'] = DATABASE_SSLROOTCERT

# Staged manifest dual-write only. Legacy reads remain active.
CASE_MEDIA_DUAL_WRITE = env_bool('CASE_MEDIA_DUAL_WRITE', False)

CASE_MEDIA_NORMALIZED_READ = env_bool('CASE_MEDIA_NORMALIZED_READ', False)
if CASE_MEDIA_NORMALIZED_READ and not CASE_MEDIA_DUAL_WRITE:
    raise ImproperlyConfigured('Normalized media reads require canonical dual-write enabled.')

# Enforced, nonce-based CSP. No external JavaScript, inline handlers or eval.
from django.utils.csp import CSP
_image_origins = [CSP.SELF, "data:", "blob:"]
if MEDIA_STORAGE == "r2":
    _image_origins.extend(image_csp_origins(R2_ENDPOINT_URL, R2_IMAGE_BUCKET, R2_IMAGE_PUBLIC_BASE_URL))
SECURE_CSP = {
    "default-src": [CSP.NONE],
    "script-src": [CSP.SELF, CSP.NONCE],
    "script-src-attr": [CSP.NONE],
    "style-src": [CSP.SELF],
    "style-src-attr": [CSP.NONE],
    "img-src": _image_origins,
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "frame-src": [CSP.NONE],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "form-action": [CSP.SELF],
}
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
# Short, host-only HSTS. Never extend to unrelated subdomains or preload.
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "300"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"
