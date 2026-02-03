from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('all-blogs/', views.all_blogs, name='all_blogs'),
    path('blog-page/<str:blog_name>/<int:blog_id>/', views.blog_page, name='blog_page'),
    path('search/', views.search, name='search'),
    path('edit-blog/<int:blog_id>/', views.edit_blog, name='edit_blog'),
    path('cookies/', views.cookies),
]