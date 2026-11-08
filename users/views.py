from django.core.exceptions import ValidationError
from users.uploads import prepare_images, store_case_images
from users.case_media import sync_uploaded_case
import os
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from .email_policy import email_user
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
            user = email_user(form.cleaned_data['email'])
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
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    auth_logout(request)
    return redirect(reverse('users:login'))

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
            try:
                with transaction.atomic():
                    user.save()
                    UserProfile.objects.create(user=user)
            except IntegrityError:
                form.add_error(None, 'No se pudo crear la cuenta. Comprueba los datos e inténtalo de nuevo.')
                return render(request, 'users/signup.html', {'form': form})

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
                user = request.user
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
                user = request.user
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
                try:
                    prepared = prepare_images(form2.cleaned_data, {
                        'header_image': [header_image], 'axial_images': axial_images,
                        'coronal_images': coronal_images, 'sagital_images': sagital_images})
                    with transaction.atomic():
                        post_instance = form.save(commit=False)
                        post_instance.author = request.user
                        post_instance.save()
                        object_metadata = store_case_images(post_instance, form2.cleaned_data, prepared)
                        if settings.CASE_MEDIA_DUAL_WRITE:
                            sync_uploaded_case(post_instance.pk, object_metadata)
                    return render(request, 'users/create_posts.html', {'form': form, 'form2': form2, 'message': 'Entrada creada.', 'error': False})
                except ValidationError as error:
                    form2.add_error(None, error)
                except Exception:
                    form2.add_error(None, 'Error de almacenamiento. No se guardó ninguna entrada. Contacta con el administrador antes de volver a intentarlo.')
                return render(request, 'users/create_posts.html', {'form': form, 'form2': form2, 'message': 'No se guardó ninguna entrada.', 'error': True})
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
            user = email_user(form.cleaned_data['email'])
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
                return redirect(reverse('blog:home'))
        else:
            return redirect(reverse('blog:home'))
    else:
        return redirect(reverse('blog:home'))
