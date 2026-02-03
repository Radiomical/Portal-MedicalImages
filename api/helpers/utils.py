from api.views import error_page
from rest_framework.views import exception_handler

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        if response.status_code == 401:
            return error_page(context['request'], 401)
        return response