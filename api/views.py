from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.urls import reverse
from blog.models import Post
from rest_framework import serializers
from django.contrib.auth.models import User
from django.shortcuts import render

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def post_urls(request):
    posts = Post.objects.all()
    post_data = []

    for post in posts:
        user = post.author
        user_data = UserSerializer(user).data
        post_dict = {
            'titulo': post.title,
            'autor': user_data,
            'categoria': post.category,
            'url': request.build_absolute_uri(reverse('blog:blog_page', args=[post.title, post.pk]))
        }
        post_data.append(post_dict)

    return Response(post_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

def error_page(request, error_code):
    return render(request, 'api/401.html', {'error_code': error_code})