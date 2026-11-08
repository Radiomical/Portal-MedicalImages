from django.db import transaction
from django.core.exceptions import ValidationError
from users.uploads import prepare_images, store_case_images
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, OuterRef, Subquery
from django.core.files.storage import default_storage
from django.http import JsonResponse, Http404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from users.models import FilePost
from .models import Post
from users.models import UserProfile
from users.forms import PostForm, FilePostForm

def cookies (request):

     return render(request, "aviso-cookies.html")

def home(request):
    posts = case_cards().order_by('-date_posted', '-pk')[:5]
    post_images = retrieve_first_post_image(posts)

    return render(request, 'blog/home.html', {'posts': posts, 'post_images': post_images})


def all_blogs(request):
    posts = case_cards().order_by('-date_posted', '-pk')
    paginator = Paginator(posts, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    post_images = retrieve_first_post_image(page_obj.object_list)

    return render(request, 'blog/all_blog_pages.html', {'post_images': post_images, 'page_obj': page_obj})


def blog_page(request, blog_name, blog_id):
    post = get_object_or_404(Post.objects.select_related('author'), id=blog_id)
    user_profile = UserProfile.objects.filter(user=post.author).first()
    country = academic_year = work_location = medical_specialty = ''
    if user_profile is not None:
        country = user_profile.country
        academic_year = user_profile.academic_year
        work_location = user_profile.work_location
        medical_specialty = user_profile.medical_specialty


    filepost = FilePost.objects.filter(post=post).first()
    # Only counts and descriptions enter the page, never an entire signed stack.
    series = {}
    for plane in ('axial', 'coronal', 'sagital'):
        field = plane + '_images'
        rows = FilePost.objects.filter(post=post).exclude(**{field: None}).exclude(**{field: ''}).order_by('pk')
        count = rows.count()
        description = rows.exclude(**{plane + '_description': None}).exclude(**{plane + '_description': ''}).exclude(**{plane + '_description': 'None'}).values_list(plane + '_description', flat=True).first() or ''
        series[plane] = {'count': count, 'description': description}
    axial_description = series['axial']['description']
    coronal_description = series['coronal']['description']
    sagital_description = series['sagital']['description']
    axial_post_images_list = series['axial']['count']
    coronal_post_images_list = series['coronal']['count']
    sagital_post_images_list = series['sagital']['count']

    if request.user == post.author:
        can_edit = True
    else:
        can_edit = False


    return render(request, 'blog/blog_page.html', {'blog_name': blog_name, 'post': post, 'axial_post_images_list': axial_post_images_list, 'coronal_post_images_list': coronal_post_images_list, 'sagital_post_images_list': sagital_post_images_list, 'can_edit': can_edit, 'filepost': filepost, 'country': country, 'academic_year': academic_year, 'work_location': work_location, 'medical_specialty': medical_specialty, 'axial_description': axial_description, 'coronal_description': coronal_description, 'sagital_description': sagital_description})


def case_cards():
    """One cover subquery and author join, not one media query per card."""
    cover = FilePost.objects.filter(post_id=OuterRef('pk')).order_by('pk').values('header_image')[:1]
    return Post.objects.select_related('author').annotate(cover_key=Subquery(cover))


def retrieve_first_post_image(posts):
    return {post.pk: default_storage.url(post.cover_key) for post in posts if post.cover_key}


@require_GET
@never_cache
def series_slice(request, blog_id, plane):
    """Preserve the current case audience; callers cannot supply an object key.

    R2 signing is local. A response authorizes only the requested image and one
    adjacent prefetch. It does not fetch the objects or list the R2 bucket.
    """
    if plane not in ('axial', 'coronal', 'sagital'):
        raise Http404
    post = get_object_or_404(Post, pk=blog_id)
    try:
        index = int(request.GET.get('index', '0'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid slice index.'}, status=400)
    field = plane + '_images'
    rows = FilePost.objects.filter(post=post).exclude(**{field: None}).exclude(**{field: ''}).order_by('pk')
    total = rows.count()
    if index < 0 or index >= total:
        raise Http404
    keys = list(rows.values_list(field, flat=True)[index:index + 2])
    from django.conf import settings
    ttl = settings.R2_SIGNED_URL_SECONDS if settings.MEDIA_STORAGE == 'r2' else 300
    return JsonResponse({'index': index, 'total': total, 'ttl': ttl,
                         'images': [{'index': index + offset, 'url': default_storage.url(key)} for offset, key in enumerate(keys)]})


def search(request):
    query = request.GET.get('q')
    post_images = {}

    if query:
        posts = case_cards().filter(Q(title__icontains=query) | Q(content__icontains=query)).order_by('-date_posted', '-pk')
    else:
        posts = Post.objects.none()

    paginator = Paginator(posts, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    post_images = retrieve_first_post_image(page_obj.object_list)

    return render(request, 'blog/search_blog.html', {'posts': posts, 'post_images': post_images, 'page_obj': page_obj, 'query': query})


@login_required(login_url='users:login')
def edit_blog(request, blog_id):
    post = get_object_or_404(Post, id=blog_id)
    if request.user != post.author:
        return redirect('blog:home')
    else:
        if request.method == 'POST':
            form = PostForm(request.POST, instance=post)
            form2 = FilePostForm(request.POST, request.FILES)
            axial_images = request.FILES.getlist('axial_image')
            coronal_images = request.FILES.getlist('coronal_image')
            sagital_images = request.FILES.getlist('sagital_image')
            header_image = request.FILES.get('header_image')

            if form.is_valid() and form2.is_valid():
                try:
                    prepared = prepare_images(form2.cleaned_data, {
                        'header_image': [header_image], 'axial_images': axial_images,
                        'coronal_images': coronal_images, 'sagital_images': sagital_images})
                    with transaction.atomic():
                        post_instance = form.save()
                        previous_ids = list(FilePost.objects.filter(post=post_instance).values_list('pk', flat=True))
                        store_case_images(post_instance, form2.cleaned_data, prepared)
                        FilePost.objects.filter(pk__in=previous_ids).delete()
                    return redirect('blog:blog_page', blog_name=post_instance.title, blog_id=post_instance.pk)
                except ValidationError as error:
                    form2.add_error(None, error)
                except Exception:
                    form2.add_error(None, 'Storage failed. Case changes were not saved. Contact the administrator before retrying.')
                return render(request, 'blog/edit_blog_page.html', {'form': form, 'form2': form2, 'post': post, 'post_id': post.pk, 'editing': True, 'error': True, 'message': 'Case changes were not saved.'})

            else:
                content = request.POST.get('content')
                title = request.POST.get('title')
                fisiopathology = request.POST.get('fisiopathology')
                clinical_case = request.POST.get('clinical_case')
                clinical_signs = request.POST.get('clinical_signs')
                doppler = request.POST.get('doppler')
                preparation = request.POST.get('preparation')
                sequential = request.POST.get('sequential')
                pediatrics = request.POST.get('pediatrics')
                medical_report = request.POST.get('medical_report')
                seram_link = request.POST.get('seram_link')
                radiopedia_link = request.POST.get('radiopedia_link')
                post_id = post.pk

                post = get_object_or_404(Post, id=blog_id)

                return render(request, 'blog/edit_blog_page.html', {'form': form, 'form2': form2, 'post': post, 'editing': True, 'title': title, 'content': content, 'fisiopathology': fisiopathology, 'clinical_case': clinical_case, 'clinical_signs': clinical_signs, 'doppler': doppler, 'preparation': preparation, 'sequential': sequential, 'pediatrics': pediatrics, 'medical_report': medical_report, 'seram_link': seram_link, 'radiopedia_link': radiopedia_link, 'post_id': post_id})
        else:
            content = post.content
            title = post.title
            fisiopathology = post.fisiopathology
            clinical_case = post.clinical_case
            clinical_signs = post.clinical_signs
            doppler = post.doppler
            preparation = post.preparation
            sequential = post.sequential
            pediatrics = post.pediatrics
            medical_report = post.medical_report
            seram_link = post.seram_link
            radiopedia_link = post.radiopedia_link

            form = PostForm(instance=post)
            form2 = FilePostForm()
            post_id = post.pk

            return render(request, 'blog/edit_blog_page.html', {'form': form, 'form2': form2, 'post': post, 'editing': True, 'title': title, 'content': content, 'fisiopathology': fisiopathology, 'clinical_case': clinical_case, 'clinical_signs': clinical_signs, 'doppler': doppler, 'preparation': preparation, 'sequential': sequential, 'pediatrics': pediatrics, 'medical_report': medical_report, 'seram_link': seram_link, 'radiopedia_link': radiopedia_link, 'post_id': post_id})