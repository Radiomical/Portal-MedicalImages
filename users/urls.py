from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('signup/', views.signup, name='signup'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('profile/', views.user_dashboard, name='user_dashboard'),
    path('profile/edit/', views.update_user_profile, name='update_user_profile'),
    path('profile/new-post/', views.new_post, name='new_post'),
    path('activate/<uidb64>/<token>/', views.activate_user, name='activate_user'),
    path('reset-password/<uidb64>/<token>/', views.reset_password_confirm, name='reset_password_confirm'),
]