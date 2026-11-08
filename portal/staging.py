"""Restrictions for a synthetic-only, public preview."""
from django.http import HttpResponseForbidden, HttpResponseNotFound

class ReadOnlyPreviewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            return HttpResponseForbidden('This synthetic preview is read-only.')
        if request.path.startswith(('/admin/', '/xxx/', '/api/')) or (request.path.startswith('/users/') and request.path != '/users/login/'):
            return HttpResponseNotFound('Not available in the synthetic preview.')
        return self.get_response(request)


def preview_context(request):
    return {'synthetic_preview': True}
