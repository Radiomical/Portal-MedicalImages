from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from users.uploads import prepare_images, store_case_images
from users.case_media import sync_uploaded_case
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, OuterRef, Subquery
from django.core.files.storage import default_storage
from django.http import JsonResponse, Http404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from users.media_reader import normalized_case
from users.models import Case, FilePost
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
    normalized = normalized_case(post.pk)
    if normalized is not None:
        from django.db.models import Count
        details = {row['plane']: row for row in normalized.series.annotate(image_count=Count('images')).values('plane', 'description', 'image_count')}
        for plane in ('axial', 'coronal', 'sagital'):
            row = details.get(plane, {})
            series[plane] = {'count': row.get('image_count', 0), 'description': row.get('description', '')}
    else:
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
    if settings.CASE_MEDIA_NORMALIZED_READ:
        from django.db.models import Case as WhenCase, When, F, CharField
        return Post.objects.select_related('author').annotate(
            cover_key=WhenCase(When(media_case__projection_stale=False, then=F('media_case__cover_key')), default=Subquery(cover), output_field=CharField()))
    return Post.objects.select_related('author').annotate(cover_key=Subquery(cover))


def retrieve_first_post_image(posts):
    return {post.pk: default_storage.url(post.cover_key) for post in posts if post.cover_key}


@require_GET
@never_cache
def series_slice(request, blog_id, plane):
    """Bounded URLs only: no object GET/LIST, and no change to case audience.

    Defaults preserve the two-image response. Adaptive clients may request up to
    16 in either direction, with at most 21 total; callers cannot supply object keys or request a stack.
    """
    if plane not in ('axial', 'coronal', 'sagital'):
        raise Http404
    try:
        index = int(request.GET.get('index', '0'))
        before = int(request.GET.get('before', '0'))
        after = int(request.GET.get('after', '1'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid slice window.'}, status=400)
    if not 0 <= before <= 16 or not 0 <= after <= 16 or before + after > 20:
        return JsonResponse({'error': 'Slice window exceeds the bounded limit.'}, status=400)
    if index < 0:
        raise Http404
    start = max(0, index - before)
    stop = index + after + 1
    normalized = normalized_case(blog_id)
    if normalized is not None:
        from users.models import Image
        from django.db.models import Count, Min, Max
        series = normalized.series.filter(plane=plane).first()
        if series is None:
            raise Http404
        rows = Image.objects.filter(series=series)
        stats = rows.aggregate(total=Count('pk'), first=Min('position'), last=Max('position'))
        total = stats['total']
        expected = series.expected_image_count
        if expected is None or total != expected or (total and (stats['first'] != 0 or stats['last'] != total - 1)):
            return JsonResponse({'error': 'Image projection unavailable.'}, status=503)
        if index >= total:
            raise Http404
        keys = list(rows.filter(position__gte=start, position__lt=stop).order_by('position').values_list('object_key', flat=True))
        if len(keys) != min(stop, total) - start:
            return JsonResponse({'error': 'Image projection unavailable.'}, status=503)
    else:
        from django.db.models import Count, Window
        field = plane + '_images'
        # COUNT OVER is evaluated before LIMIT/OFFSET: total and bounded keys in
        # one DB round trip. The FK already ties every returned row to this case.
        rows = (FilePost.objects.filter(post_id=blog_id)
                .exclude(**{field: None}).exclude(**{field: ''})
                .annotate(series_total=Window(expression=Count('pk'))).order_by('pk'))
        batch = list(rows.values_list(field, 'series_total')[start:stop])
        if not batch:
            raise Http404
        total = batch[0][1]
        if index >= total:
            raise Http404
        keys = [key for key, _ in batch]
    ttl = settings.R2_SIGNED_URL_SECONDS if settings.MEDIA_STORAGE == 'r2' else 300
    return JsonResponse({'index': index, 'total': total, 'ttl': ttl,
                         'images': [{'index': start + offset, 'url': default_storage.url(key)} for offset, key in enumerate(keys)]})



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
                        object_metadata = store_case_images(post_instance, form2.cleaned_data, prepared)
                        FilePost.objects.filter(pk__in=previous_ids).delete()
                        if settings.CASE_MEDIA_DUAL_WRITE:
                            sync_uploaded_case(post_instance.pk, object_metadata)
                    return redirect('blog:blog_page', blog_name=post_instance.title, blog_id=post_instance.pk)
                except ValidationError as error:
                    form2.add_error(None, error)
                except Exception:
                    form2.add_error(None, 'Storage failed. Case changes were not saved. Contact the administrator before retrying.')
                return render(request, 'blog/edit_blog_page.html', {'form': form, 'form2': form2, 'post': post, 'post_id': post.pk, 'editing': True, 'error': True, 'message': 'No se guardaron los cambios de la entrada.'})

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