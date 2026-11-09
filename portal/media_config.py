"""Validation shared by public-image URLs and the image-only CSP allowlist."""
import ipaddress
import re
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured


def validate_public_image_origin(value):
    """Accept an HTTPS custom-domain origin, never a signed/development URL."""
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
    except ValueError as error:
        raise ImproperlyConfigured('Invalid R2_IMAGE_PUBLIC_BASE_URL') from error
    labels = host.split('.')
    valid_host = len(labels) >= 2 and len(host) <= 253 and all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
        for label in labels
    )
    try:
        ipaddress.ip_address(host)
        valid_host = False
    except ValueError:
        pass
    if (any(ord(c) < 33 or ord(c) == 127 for c in value) or parsed.scheme != 'https' or not valid_host
            or parsed.netloc != host or parsed.path not in {'', '/'}
            or '?' in value or '#' in value
            or host == 'r2.dev' or host.endswith('.r2.dev')
            or host == 'r2.cloudflarestorage.com' or host.endswith('.r2.cloudflarestorage.com')):
        raise ImproperlyConfigured('R2_IMAGE_PUBLIC_BASE_URL must be an HTTPS custom-domain origin without a path, credentials, port, query or fragment')
    return 'https://' + host


def image_csp_origins(endpoint_url, image_bucket, public_base_url=''):
    """Only exact media origins; never add an origin to scripts or connections."""
    origins = []
    endpoint = urlsplit(endpoint_url)
    if (endpoint.scheme == 'https' and endpoint.hostname
            and endpoint.hostname.endswith('.r2.cloudflarestorage.com')
            and endpoint.netloc == endpoint.hostname):
        origins.append('https://' + endpoint.hostname)
        if image_bucket and all(c.isalnum() or c == '-' for c in image_bucket):
            origins.append('https://' + image_bucket + '.' + endpoint.hostname)
    public_origin = validate_public_image_origin(public_base_url)
    if public_origin:
        origins.append(public_origin)
    return origins
