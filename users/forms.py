import os
import pycountry
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Post, FilePost, UserProfile
from django.db.models.fields import BLANK_CHOICE_DASH



class SignupForm (UserCreationForm):

    email = forms.EmailField()
    username = forms.CharField(max_length=30, error_messages={'required': 'Por favor ingresa tu nombre de usuario'})
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def clean_username(self):

        username = self.cleaned_data['username']

        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('El nombre de usuario ya existe')

        if 'admin' in username:
            raise forms.ValidationError('El nombre de usuario ya existe')

        return username

    def clean(self):

        cleaned_data = super(SignupForm, self).clean()
        email = cleaned_data.get('email')
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')


        if password1 != password2:
            raise forms.ValidationError('Las contraseñas no coinciden')

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('El correo ya existe')

        if password1 and len(password1) < 8:
            raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres')

        if password1 and not any(char.isdigit() for char in password1):
            raise forms.ValidationError('La contraseña debe tener al menos un número')

        if password1 and not any(char.isupper() for char in password1):
            raise forms.ValidationError('La contraseña debe tener al menos una mayúscula')

        if password1 and not any(char.islower() for char in password1):
            raise forms.ValidationError('La contraseña debe tener al menos una minúscula')

        else:
            return cleaned_data

class UserUpdateForm(forms.Form):
    user_country = forms.ChoiceField(choices=BLANK_CHOICE_DASH + [(country.name, country.name) for country in pycountry.countries], label='País', required=False)
    user_academic_year = forms.ChoiceField(choices=BLANK_CHOICE_DASH + [(academic_year, academic_year) for academic_year in UserProfile.academic_year_list], label='Año de formación', required=False)
    user_work_location = forms.CharField(max_length=100, required=False, label='Centro de trabajo')
    user_medical_specialty = forms.ChoiceField(choices=BLANK_CHOICE_DASH + [(medical_specialty, medical_specialty) for medical_specialty in UserProfile.medical_specialty_list], label='Especialidad médica', required=False)

    class Meta:
        model = UserProfile
        fields = ['user_country', 'user_academic_year', 'user_work_location', 'user_medical_specialty']

class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

class ResetPasswordForm(forms.Form):
    email = forms.EmailField()

class ChangePasswordForm(forms.Form):
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    def clean(self):

            cleaned_data = super(ChangePasswordForm, self).clean()
            password1 = cleaned_data.get('password1')
            password2 = cleaned_data.get('password2')

            if password1 != password2:
                raise forms.ValidationError('Las contraseñas no coinciden')

            if password1 and len(password1) < 8:
                raise forms.ValidationError('La contraseña debe tener al menos 8 caracteres')

            if password1 and not any(char.isdigit() for char in password1):
                raise forms.ValidationError('La contraseña debe tener al menos un número')

            if password1 and not any(char.isupper() for char in password1):
                raise forms.ValidationError('La contraseña debe tener al menos una mayúscula')

            if password1 and not any(char.islower() for char in password1):
                raise forms.ValidationError('La contraseña debe tener al menos una minúscula')

            else:
                return cleaned_data

class PostForm(forms.ModelForm):

    title = forms.CharField(max_length=100)

    class Meta:
        model = Post
        fields = ['title', 'content', 'category', 'fisiopathology', 'clinical_case', 'clinical_signs', 'doppler', 'medical_findings', 'preparation', 'sequential', 'pediatrics', 'medical_report', 'seram_link', 'radiopedia_link']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].widget.input_type = 'text'
        self.fields['fisiopathology'].widget.input_type = 'text'
        self.fields['clinical_case'].widget.input_type = 'text'
        self.fields['clinical_signs'].widget.input_type = 'text'
        self.fields['doppler'].widget.input_type = 'text'
        self.fields['preparation'].widget.input_type = 'text'
        self.fields['sequential'].widget.input_type = 'text'
        self.fields['pediatrics'].widget.input_type = 'text'
        self.fields['medical_report'].widget.input_type = 'text'
        self.fields['seram_link'].widget.input_type = 'URL'
        self.fields['radiopedia_link'].widget.input_type = 'URL'

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/jpg"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
            extensions = set([os.path.splitext(d.name)[1].lower() for d in result])
            if any(ext not in ['.jpeg', '.jpg', '.dcm'] for ext in extensions):
                raise forms.ValidationError("Solo se permiten imágenes en formato JPEG/JPG o DICOM")
        else:
            result = single_file_clean(data, initial)
        return result

class FilePostForm(forms.ModelForm):
    header_image = forms.FileField(label='Imagen de cabecera', widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/jpg'}))
    axial_image = MultipleImageField(label='Axial', required=False)
    axial_description = forms.CharField(max_length=500, label='Descripción axial', required=False)
    coronal_image = MultipleImageField(label='Coronal', required=False)
    coronal_description = forms.CharField(max_length=500, label='Descripción coronal', required=False)
    sagital_image = MultipleImageField(label='Sagital', required=False)
    sagital_description = forms.CharField(max_length=500, label='Descripción sagital', required=False)
    format = forms.ChoiceField(choices=FilePost.FORMAT_CHOICES, widget=forms.RadioSelect, label='Formato')
    accepted_data_use = forms.ChoiceField(choices=FilePost.USE_DATA_CHOICES, widget=forms.RadioSelect, label='¿Acepta el uso de sus datos?', initial='No')
    cie_11_tagging = forms.ChoiceField(choices=FilePost.CIE_11_TAGGING_CHOICES, widget=forms.RadioSelect, label='Etiquetado CIE-11', required=False)
    interested_region = forms.ChoiceField(choices=FilePost.INTERESTED_REGION_CHOICES, widget=forms.RadioSelect, label='Región de interés', required=False)
    other_interested_region = forms.CharField(max_length=100, label='Otra región de interés', required=False)

    def clean(self):
        cleaned_data = super(FilePostForm, self).clean()
        header_image = cleaned_data.get('header_image')
        format = cleaned_data.get('format')
        axial_image = cleaned_data.get('axial_image')
        coronal_image = cleaned_data.get('coronal_image')
        sagital_image = cleaned_data.get('sagital_image')

        if axial_image is not None:
            if format == 'DICOM':
                if not all(os.path.splitext(d.name)[1].lower() == '.dcm' for d in axial_image):
                    raise forms.ValidationError("Todas las imágenes deben estar en formato DICOM")
            else:
                if not all(os.path.splitext(d.name)[1].lower() in ['.jpeg', '.jpg'] for d in axial_image):
                    raise forms.ValidationError("Todas las imágenes deben estar en formato JPEG/JPG")

        if coronal_image is not None:
            if format == 'DICOM':
                if not all(os.path.splitext(d.name)[1].lower() == '.dcm' for d in coronal_image):
                    raise forms.ValidationError("Todas las imágenes deben estar en formato DICOM")
            else:
                if not all(os.path.splitext(d.name)[1].lower() in ['.jpeg', '.jpg'] for d in coronal_image):
                    raise forms.ValidationError("Todas las imágenes deben estar en formato JPEG/JPG")

        if sagital_image is not None:
            if format == 'DICOM':
                if not all(os.path.splitext(d.name)[1].lower() == '.dcm' for d in sagital_image):
                    raise forms.ValidationError("Todas las imágenes deben estar en formato DICOM")
            else:
                if not all(os.path.splitext(d.name)[1].lower() in ['.jpeg', '.jpg'] for d in sagital_image):
                    raise forms.ValidationError("Todas las imágenes deben estar en formato JPEG/JPG")

        if header_image is not None:
            extension = os.path.splitext(header_image.name)[1].lower()
            if format == 'DICOM':
                if extension not in ['.dcm']:
                    raise forms.ValidationError("Todas las imágenes deben estar en formato DICOM")
            else:
                if extension not in ['.jpeg', '.jpg']:
                    raise forms.ValidationError("La imagen debe estar en formato JPEG/JPG")

    class Meta:
        model = FilePost
        fields = ['format', 'header_image', 'axial_image', 'axial_description', 'coronal_image', 'coronal_description', 'sagital_image', 'sagital_description', 'accepted_data_use', 'cie_11_tagging', 'interested_region', 'other_interested_region']