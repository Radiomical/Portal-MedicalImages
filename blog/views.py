from django.db import transaction
from django.core.exceptions import ValidationError
from users.uploads import prepare_images, store_case_images
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from users.models import FilePost
from .models import Post
from users.models import UserProfile
from users.forms import PostForm, FilePostForm

def cookies (request):

     return render(request, "aviso-cookies.html")

def home(request):
    posts = Post.objects.order_by('-date_posted')[:5]
    post_images = retrieve_first_post_image(posts)

    return render(request, 'blog/home.html', {'posts': posts, 'post_images': post_images})


def all_blogs(request):
    posts = Post.objects.order_by('-date_posted')
    paginator = Paginator(posts, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    post_images = retrieve_first_post_image(page_obj.object_list)

    return render(request, 'blog/all_blog_pages.html', {'post_images': post_images, 'page_obj': page_obj})


def blog_page(request, blog_name, blog_id):
    post = get_object_or_404(Post, id=blog_id)
    user_profile = UserProfile.objects.filter(user=post.author).first()
    country = academic_year = work_location = medical_specialty = ''
    if user_profile is not None:
        country = user_profile.country
        academic_year = user_profile.academic_year
        work_location = user_profile.work_location
        medical_specialty = user_profile.medical_specialty


    filepost = FilePost.objects.filter(post=post).first()
    files = FilePost.objects.filter(post=post)
    axial_post_images_list = list()
    coronal_post_images_list = list()
    sagital_post_images_list = list()
    axial_description = str()
    coronal_description = str()
    sagital_description = str()

    for file in files:
        if file.axial_images:
            axial_post_images_list.append(file.axial_images.url)
            if file.axial_description and file.axial_description != 'None':
                if not axial_description:
                    axial_description = file.axial_description
        if file.coronal_images:
            coronal_post_images_list.append(file.coronal_images.url)
            if file.coronal_description and file.coronal_description != 'None':
                if not coronal_description:
                    coronal_description = file.coronal_description
        if file.sagital_images:
            if file.sagital_description and file.sagital_description != 'None':
                if not sagital_description:
                    sagital_description = file.sagital_description
            sagital_post_images_list.append(file.sagital_images.url)

    if request.user == post.author:
        can_edit = True
    else:
        can_edit = False


    return render(request, 'blog/blog_page.html', {'blog_name': blog_name, 'post': post, 'axial_post_images_list': axial_post_images_list, 'coronal_post_images_list': coronal_post_images_list, 'sagital_post_images_list': sagital_post_images_list, 'can_edit': can_edit, 'filepost': filepost, 'country': country, 'academic_year': academic_year, 'work_location': work_location, 'medical_specialty': medical_specialty, 'axial_description': axial_description, 'coronal_description': coronal_description, 'sagital_description': sagital_description})


def retrieve_first_post_image(posts):
    post_images = {}

    for post in posts:
        file = FilePost.objects.filter(post=post).first()
        if file is not None:
            post_images[post.id] = file.header_image.url

    return post_images

def search(request):
    query = request.GET.get('q')
    post_images = {}

    if query:
        posts = Post.objects.filter(Q(title__icontains=query) | Q(content__icontains=query)).order_by('-date_posted')
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