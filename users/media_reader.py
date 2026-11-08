"""Default-off DB manifest reader, preserving legacy fallback and case audience."""
from django.conf import settings
from .models import Case


def normalized_case(post_id):
    if not settings.CASE_MEDIA_NORMALIZED_READ:
        return None
    return Case.objects.filter(pk=post_id, projection_stale=False).first()
