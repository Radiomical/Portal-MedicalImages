import pydicom
import os
from PIL import Image
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db import transaction
from django.contrib.sites.shortcuts import get_current_site
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from users.helpers.tokens import account_activation_token, reset_password_token
from django.template.loader import render_to_string
from django.urls import reverse
from .forms import SignupForm, LoginForm, ResetPasswordForm, ChangePasswordForm, PostForm, FilePostForm, UserUpdateForm
from .models import Post, FilePost, UserProfile
from django.contrib.auth.models import User
from blog.models import Post
from blog.views import retrieve_first_post_image

def login(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            return redirect(reverse('users:user_dashboard'))

        else:
            form = LoginForm()
            return render(request, 'users/login.html', {'form': form})

    elif request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = User.objects.filter(email=form.cleaned_data['email']).first()
            if user and user.check_password(form.cleaned_data['password']):
                if user.is_active:
                    auth_login(request, user)
                    return redirect(reverse('users:user_dashboard'))
                else:
                    return render(request, 'users/login.html', {'form': form, 'error_message': 'Tu cuenta no está activa. Revisa tu correo electrónico para activarla.'})
            else:
                return render(request, 'users/login.html', {'form': form, 'error_message': 'Correo o contraseña incorrectos.'})
        else:
            return render(request, 'users/login.html', {'form': form})

    else:
        return redirect('blog:home')

def logout(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            auth_logout(request)
            return redirect(reverse('users:login'))
        else:
            return redirect(reverse('users:login'))
    else:
        return redirect('blog:home')

def signup(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            return redirect(reverse('users:user_dashboard'))

        form = SignupForm()
        return render(request, 'users/signup.html', {'form': form})

    elif request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.password = make_password(form.cleaned_data['password1'])
            user.is_active = False
            user.save()

            UserProfile.objects.create(user=user)

            current_site = get_current_site(request)

            subject = render_to_string('users/activation_email_subject.txt')
            message = render_to_string('users/activation_email_message.txt', {
                'user': user,
                'domain': current_site.domain,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': account_activation_token.make_token(user),
            })

            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )

            if user.email:
                msg = 'Usuario creado correctamente. Verifica tu correo electrónico para activar la cuenta.'

            else:
                msg = 'Error al crear el usuario. Por favor intenta de nuevo.'

            return render(request, 'users/signup.html', {'message': msg})
        else:
            return render(request, 'users/signup.html', {'form': form})

    else:
        return redirect('blog:home')

def update_user_profile(request):
    if not request.user.is_authenticated:
        return redirect(reverse('users:login'))
    else:
        if request.method == 'GET':
            form = ChangePasswordForm()
            form2 = UserUpdateForm()
            get_current_user_mail = request.user.email
            return render(request, 'users/user_dashboard.html', {'form': form, 'form2': form2, 'email': get_current_user_mail})

        elif request.method == 'POST':
            form = ChangePasswordForm()
            form2 = UserUpdateForm(request.POST)
            if form2.is_valid():
                user = User.objects.get(email=request.user.email)
                country = form2.cleaned_data['user_country']
                academic_year = form2.cleaned_data['user_academic_year']
                work_location = form2.cleaned_data['user_work_location']
                medical_specialty = form2.cleaned_data['user_medical_specialty']

                UserProfile.objects.filter(user=user).update(country=country, academic_year=academic_year, work_location=work_location, medical_specialty=medical_specialty)

                get_current_user_mail = request.user.email
                message = 'Información actualizada correctamente.'

                return render(request, 'users/user_dashboard.html', {'message': message, 'form': form, 'form2': form2, 'email': get_current_user_mail})
            else:
                get_current_user_mail = request.user.email
                return render(request, 'users/user_dashboard.html', {'form': form, 'form2': form2, 'email': get_current_user_mail})

        else:
            return redirect('blog:home')

def user_dashboard(request):
    if not request.user.is_authenticated:
        return redirect(reverse('users:login'))
    else:
        if request.method == 'GET':
            form = ChangePasswordForm()
            form2 = UserUpdateForm()
            get_current_user_mail = request.user.email
            return render(request, 'users/user_dashboard.html', {'form': form, 'form2': form2, 'email': get_current_user_mail})

        elif request.method == 'POST':
            form = ChangePasswordForm(request.POST)
            form2 = UserUpdateForm()
            if form.is_valid():
                user = User.objects.get(email=request.user.email)
                user.password = make_password(form.cleaned_data['password1'])
                user.save()

                get_current_user_mail = request.user.email
                message = 'Contraseña actualizada correctamente.'

                auth_login(request, user)

                return render(request, 'users/user_dashboard.html', {'message': message, 'form': form, 'form2': form2, 'email': get_current_user_mail})
            else:
                get_current_user_mail = request.user.email
                return render(request, 'users/user_dashboard.html', {'form': form, 'form2': form2, 'email': get_current_user_mail})

        else:
            return redirect('blog:home')

@transaction.atomic
def new_post(request):
    if not request.user.is_authenticated:
        return redirect(reverse('users:login'))
    else:
        if request.method == 'GET':
            form = PostForm()
            form2 = FilePostForm()
            return render(request, 'users/create_posts.html', {'form': form, 'form2': form2, 'show_popup': True})

        elif request.method == 'POST':
            form = PostForm(request.POST)
            form2 = FilePostForm(request.POST, request.FILES)
            axial_images = request.FILES.getlist('axial_image')
            coronal_images = request.FILES.getlist('coronal_image')
            sagital_images = request.FILES.getlist('sagital_image')
            header_image = request.FILES.get('header_image')

            if form.is_valid() and form2.is_valid():
                title = form.cleaned_data['title']
                content = form.cleaned_data['content']
                category = form.cleaned_data['category']
                image_format = form2.cleaned_data['format']
                fisiopathology = form.cleaned_data['fisiopathology']
                clinical_case = form.cleaned_data['clinical_case']
                clinical_signs = form.cleaned_data['clinical_signs']
                doppler = form.cleaned_data['doppler']
                sequential = form.cleaned_data['sequential']
                preparation = form.cleaned_data['preparation']
                pediatrics = form.cleaned_data['pediatrics']
                medical_report = form.cleaned_data['medical_report']
                seram_link = form.cleaned_data['seram_link']
                radiopedia_link = form.cleaned_data['radiopedia_link']
                accepted_data_use = form2.cleaned_data['accepted_data_use']
                cie_11_tagging = form2.cleaned_data['cie_11_tagging']
                interested_region = form2.cleaned_data['interested_region']
                other_interested_region = form2.cleaned_data['other_interested_region']
                axial_description = form2.cleaned_data['axial_description']
                coronal_description = form2.cleaned_data['coronal_description']
                sagital_description = form2.cleaned_data['sagital_description']
                error = False

                if accepted_data_use == 'No':
                    cie_11_tagging = None
                    interested_region = None
                    other_interested_region = None

                post_instance = Post.objects.create(title=title, content=content, category=category, author=request.user, fisiopathology=fisiopathology, clinical_case=clinical_case, clinical_signs=clinical_signs, doppler=doppler, preparation=preparation, pediatrics=pediatrics, medical_report=medical_report, seram_link=seram_link, radiopedia_link=radiopedia_link)

                if image_format == 'DICOM':
                    try:
                        image_header_dicom = pydicom.dcmread(header_image)
                        image_header_array = image_header_dicom.pixel_array.astype(float)
                        new_image_header = Image.fromarray(image_header_array)
                        new_image_header = new_image_header.convert('L')
                        output_filename_header = header_image.name.split('.')[0] + '.jpg'
                        output_path_image_header = 'media/images/user_{0}/post_{1}/{2}'.format(post_instance.author.username, post_instance.pk, output_filename_header)
                        os.makedirs(os.path.dirname(output_path_image_header), exist_ok=True)
                        new_image_header.save(output_path_image_header, format='JPEG')
                        output_path_image_header = output_path_image_header.replace('media/', '')

                        if not [x for x in (axial_images, sagital_images, coronal_images) if x]:
                            FilePost.objects.create(post=post_instance, format=image_format, header_image=output_path_image_header, accepted_data_use=accepted_data_use, cie_11_tagging=cie_11_tagging, interested_region=interested_region, other_interested_region=other_interested_region)


                        for image_set in [axial_images, sagital_images, coronal_images]:
                            for image in image_set:
                                dicom_data = pydicom.dcmread(image)
                                image_array = dicom_data.pixel_array.astype(float)
                                img = Image.fromarray(image_array)
                                img = img.convert('L')
                                output_filename = image.name.split('.')[0] + '.jpg'
                                output_path_image = 'media/images/user_{0}/post_{1}/{2}'.format(post_instance.author.username, post_instance.pk, output_filename)
                                os.makedirs(os.path.dirname(output_path_image), exist_ok=True)
                                if accepted_data_use == 'Si':
                                    output_path_dicom_image = 'media/images/user_{0}/post_{1}/{2}'.format(post_instance.author.username, post_instance.pk, image.name)
                                    dicom_data.save_as(output_path_dicom_image)
                                img.save(output_path_image, format='JPEG')
                                output_path_image = output_path_image.replace('media/', '')

                                if image_set is axial_images:
                                    FilePost.objects.create(axial_images=output_path_image, post=post_instance, format=image_format, header_image=output_path_image_header, axial_description=axial_description, accepted_data_use=accepted_data_use, cie_11_tagging=cie_11_tagging, interested_region=interested_region, other_interested_region=other_interested_region)
                                elif image_set is sagital_images:
                                    FilePost.objects.create(sagital_images=output_path_image, post=post_instance, format=image_format, header_image=output_path_image_header, sagital_description=sagital_description, accepted_data_use=accepted_data_use, cie_11_tagging=cie_11_tagging, interested_region=interested_region, other_interested_region=other_interested_region)
                                else:
                                    FilePost.objects.create(coronal_images=output_path_image, post=post_instance, format=image_format, header_image=output_path_image_header, coronal_description=coronal_description, accepted_data_use=accepted_data_use, cie_11_tagging=cie_11_tagging, interested_region=interested_region, other_interested_region=other_interested_region)
                    except:
                        error = True

                else:
                    if not [x for x in (axial_images, sagital_images, coronal_images) if x]:
                        FilePost.objects.create(post=post_instance, format=image_format, header_image=header_image)
                    try:
                        for image_set in [axial_images, sagital_images, coronal_images]:
                            for image in image_set:
                                if image_set is axial_images:
                                    FilePost.objects.create(axial_images=image, post=post_instance, format=image_format, header_image=header_image, axial_description=axial_description)
                                elif image_set is sagital_images:
                                    FilePost.objects.create(sagital_images=image, post=post_instance, format=image_format, header_image=header_image, sagital_description=sagital_description)
                                else:
                                    FilePost.objects.create(coronal_images=image, post=post_instance, format=image_format, header_image=header_image, coronal_description=coronal_description)
                    except:
                        error = True

                if not error:
                    message = 'Entrada creada correctamente.'
                else:
                    message = 'Error al crear la entrada. Por favor intenta de nuevo.'

                return render(request, 'users/create_posts.html', {'form': form, 'form2': form2, 'message': message, 'error': error})
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

                return render(request, 'users/create_posts.html', {'form': form, 'form2': form2, 'title': title, 'content': content, 'fisiopathology': fisiopathology, 'clinical_case': clinical_case, 'clinical_signs': clinical_signs, 'doppler': doppler, 'preparation': preparation, 'sequential': sequential, 'pediatrics': pediatrics, 'medical_report': medical_report, 'seram_link': seram_link, 'radiopedia_link': radiopedia_link})
        else:
            return redirect('blog:home')

def activate_user(request, uidb64, token, *args, **kwargs):
    if not request.user.is_authenticated:
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is not None and account_activation_token.check_token(user, token):
            user.is_active = True
            user.save()
            auth_login(request, user)
            return redirect('users:user_dashboard')
        else:
            return redirect(reverse('blog:home'))
    else:
        return redirect(reverse('blog:home'))

def reset_password(request):
    if request.user.is_authenticated:
        return redirect(reverse('users:user_dashboard'))

    if request.method == 'GET':
        form = ResetPasswordForm()
        return render(request, 'users/reset_password.html', {'form': form})

    elif request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            user = User.objects.filter(email=form.cleaned_data['email']).first()
            if user:
                user.save()

                current_site = get_current_site(request)

                subject = render_to_string('users/reset_password_email_subject.txt')
                message = render_to_string('users/reset_password_email_message.txt', {
                    'user': user,
                    'domain': current_site.domain,
                    'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                    'token': reset_password_token.make_token(user),
                })

                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )

                return render(request, 'users/reset_password.html', {'message': 'Si la cuenta existe, se enviará un correo electrónico con las instrucciones para restablecer la contraseña.'})
            else:
                return render(request, 'users/reset_password.html', {'message': 'Si la cuenta existe, se enviará un correo electrónico con las instrucciones para restablecer la contraseña.'})
        else:
            return render(request, 'users/reset_password.html', {'form': form})

    else:
        return redirect('blog:home')

def reset_password_confirm(request, uidb64, token, *args, **kwargs):
    if not request.user.is_authenticated:
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.filter(pk=uid).first()
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is not None and reset_password_token.check_token(user, token):
            if request.method == 'GET':
                form = ChangePasswordForm()
                return render(request, 'users/reset_password.html', {'form': form, 'change_password': True, 'uidb64': uidb64, 'token': token})
            elif request.method == 'POST':
                form = ChangePasswordForm(request.POST)
                if form.is_valid():
                    user.password = make_password(form.cleaned_data['password1'])
                    user.save()
                    return render(request, 'users/reset_password.html', {'message': 'Contraseña restablecida correctamente.'})
                else:
                    return render(request, 'users/reset_password.html', {'form': form, 'change_password': True, 'uidb64': uidb64, 'token': token})
            else:
                posts = Post.objects.order_by('-date_posted')[:5]
                post_images = retrieve_first_post_image(posts)

                return render(request, 'blog/home.html', {'posts': posts, 'post_images': post_images})
        else:
            return redirect(reverse('blog:home'))
    else:
        return redirect(reverse('blog:home'))
