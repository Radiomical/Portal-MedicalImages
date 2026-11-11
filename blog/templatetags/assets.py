"""Content-versioned URLs for the shared UI assets.

The collected file is authoritative in deployed images. Static finders are a
fallback for tests and local development before collectstatic. Deployments keep
static trees immutable, so each worker can cache a version for its lifetime.
"""
import hashlib
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage

register = template.Library()


@lru_cache(maxsize=64)
def versioned_asset(path):
    try:
        with staticfiles_storage.open(path, 'rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()[:12]
    except FileNotFoundError:
        resolved = finders.find(path)
        if not resolved:
            raise ValueError(f'Static asset not found: {path}')
        with Path(resolved).open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()[:12]
    url = urlsplit(staticfiles_storage.url(path))
    query = [(key, value) for key, value in parse_qsl(url.query) if key != 'v']
    query.append(('v', digest))
    return urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), url.fragment))


register.simple_tag(versioned_asset, name='versioned_static')
