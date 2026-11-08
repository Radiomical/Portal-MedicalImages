"""Static synthetic images for the preview only, never production media."""
from django.conf import settings
from django.urls import re_path
from django.views.static import serve
from .urls import urlpatterns as base_patterns
urlpatterns = [
    re_path(r'^media/(?P<path>synthetic/[a-z0-9_-]+\.jpg)$', serve,
            {'document_root': settings.MEDIA_ROOT, 'show_indexes': False}),
    *base_patterns,
]
