"""Opt-in SMTP provider configuration. Secrets only enter through environment."""
from django.core.exceptions import ImproperlyConfigured
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


def email_configuration(environ):
    provider = environ.get('EMAIL_PROVIDER', 'custom')
    if provider not in {'custom', 'resend'}:
        raise ImproperlyConfigured('EMAIL_PROVIDER must be custom or resend')
    if provider == 'resend':
        sender = environ.get('DEFAULT_FROM_EMAIL', '')
        try:
            validate_email(sender)
        except ValidationError as error:
            raise ImproperlyConfigured('Resend requires a valid DEFAULT_FROM_EMAIL on a verified sending domain') from error
        if not environ.get('EMAIL_HOST_PASSWORD', ''):
            raise ImproperlyConfigured('Resend requires EMAIL_HOST_PASSWORD from the secret store')
        # Provider mode is explicit: never fall back to console or plaintext mail.
        return {'EMAIL_PROVIDER': provider,
                'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
                'EMAIL_HOST': 'smtp.resend.com', 'EMAIL_PORT': 587,
                'EMAIL_HOST_USER': 'resend',
                'EMAIL_HOST_PASSWORD': environ['EMAIL_HOST_PASSWORD'],
                'EMAIL_USE_TLS': True, 'EMAIL_USE_SSL': False,
                'EMAIL_TIMEOUT': 20, 'DEFAULT_FROM_EMAIL': sender}
    tls_value = environ.get('EMAIL_USE_TLS', 'true').lower()
    if tls_value not in {'true', '1', 'yes', 'false', '0', 'no', ''}:
        raise ImproperlyConfigured('EMAIL_USE_TLS must be a boolean')
    return {'EMAIL_PROVIDER': provider,
            'EMAIL_BACKEND': environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'),
            'EMAIL_HOST': environ.get('EMAIL_HOST', ''),
            'EMAIL_PORT': int(environ.get('EMAIL_PORT', '587')),
            'EMAIL_USE_TLS': tls_value in {'1', 'true', 'yes'},
            'EMAIL_USE_SSL': False,
            'EMAIL_HOST_USER': environ.get('EMAIL_HOST_USER', ''),
            'EMAIL_HOST_PASSWORD': environ.get('EMAIL_HOST_PASSWORD', ''),
            'EMAIL_TIMEOUT': 20,
            'DEFAULT_FROM_EMAIL': environ.get('DEFAULT_FROM_EMAIL', 'noreply@localhost')}
