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
    # Keep the array and item schema, but bound each request. PK keysets avoid
    # growing OFFSET scans and remain stable when new cases are appended.
    try:
        after = int(request.query_params.get('after', '0'))
        page_size = int(request.query_params.get('page_size', '50'))
        if after < 0 or after > 9223372036854775807 or not 1 <= page_size <= 100:
            raise ValueError
    except (TypeError, ValueError):
        return Response({'error': 'after must be a non-negative integer and page_size must be 1-100.'}, status=400)
    posts = list(Post.objects.select_related('author').filter(pk__gt=after).order_by('pk')[:page_size + 1])
    has_more = len(posts) > page_size
    posts = posts[:page_size]
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

    response = Response(post_data)
    if has_more:
        url = request.build_absolute_uri(request.path)
        response['Link'] = f'<{url}?after={posts[-1].pk}&page_size={page_size}>; rel="next"'
    return response


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

def error_page(request, error_code):
    return render(request, 'api/401.html', {'error_code': error_code}, status=error_code)