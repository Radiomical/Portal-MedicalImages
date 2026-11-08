"""Response hardening without third-party telemetry or report collectors."""

class ResponseSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), display-capture=()')
        # HTML carries per-request CSP nonces and can include signed media URLs.
        # Do not let browser/shared caches retain it, even for anonymous users.
        content_type = response.get('Content-Type', '').split(';', 1)[0]
        if content_type == 'text/html' or getattr(request, 'user', None) and request.user.is_authenticated:
            response['Cache-Control'] = 'private, no-store'
        return response
