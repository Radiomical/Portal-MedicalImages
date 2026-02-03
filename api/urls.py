from django.urls import path
from . import views

urlpatterns = [
    path('get/posts/', views.post_urls, name='post_urls'),
]