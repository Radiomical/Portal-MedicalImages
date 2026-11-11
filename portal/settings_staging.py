"""Public, read-only synthetic preview. Never point it at a production database."""
import os
from .settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured
if DATABASES['default']['NAME'] != 'portal_staging':
    raise ImproperlyConfigured('Staging requires the dedicated portal_staging database')
DEBUG = False
ALLOWED_HOSTS = [value.strip() for value in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if value.strip()]
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
MIDDLEWARE = ['portal.staging.ReadOnlyPreviewMiddleware', *MIDDLEWARE]
SECURE_SSL_REDIRECT = False  # The tunnel terminates TLS; this listener is loopback-only.
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
ROOT_URLCONF = 'portal.urls_staging'
TEMPLATES[0]['OPTIONS']['context_processors'].append('portal.staging.preview_context')
