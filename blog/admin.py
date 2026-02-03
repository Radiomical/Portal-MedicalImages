from django.contrib import admin
from .models import Post

class AdminPost(admin.ModelAdmin):
    list_display = ('title', 'author', 'date_posted')

admin.site.register(Post, AdminPost)
