from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('s3c-panel-secret0/', admin.site.urls),
    path('', include(('blog.urls', 'blog'), namespace='blog')),
    path('users/', include(('users.urls', 'users'), namespace='users')),
    path('api/', include(('api.urls', 'api'), namespace='api')),
]

from django.conf.urls.static import static
from django.conf import settings

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)