from django.contrib import admin
from .models import FilePost, UserProfile

class AdminPost(admin.ModelAdmin):
    list_display = ('id', 'post')

class AdminUserProfile(admin.ModelAdmin):
    list_display = ('id', 'user')

admin.site.register(FilePost, AdminPost)
admin.site.register(UserProfile, AdminUserProfile)