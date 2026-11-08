from .countries import COUNTRY_CHOICES
from django.db import models
from blog.models import Post
from django.contrib.auth.models import User
from django.db.models.fields import BLANK_CHOICE_DASH


def images_path(instance, filename):
    return 'images/user_{0}/post_{1}/{2}'.format(instance.post.author.username, instance.post.id, filename)

class UserProfile(models.Model):
    academic_year_list = ['Estudiante','R0', 'R1', 'R2','R3', 'R4','R5', 'Adjunto']
    medical_specialty_list = ['Radiología pediátrica', 'Radiología ginecológica','Radiología de abdomen', 'Neurorradiología', 'Radiología intervencionista', 'Radiología musculoesquelética', 'Radiología general']

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    country = models.CharField(max_length=100, choices=COUNTRY_CHOICES, blank=True, null=True)
    academic_year = models.CharField(max_length=100, choices=[(academic_year, academic_year) for academic_year in academic_year_list], blank=True, null=True)
    work_location = models.CharField(max_length=100, blank=True, null=True)
    medical_specialty = models.CharField(max_length=100, choices=[(medical_specialty, medical_specialty) for medical_specialty in medical_specialty_list], blank=True, null=True)

class FilePost(models.Model):
    USE_DATA_CHOICES = (
        ('Si', 'Si'),
        ('No', 'No'),
    )

    JPEG = 'JPEG'
    DICOM = 'DICOM'
    FORMAT_CHOICES = (
        ('JPEG, JPG', 'JPEG/JPG'),
        (DICOM, 'DICOM'),
    )

    INTERESTED_REGION_CHOICES = (
        BLANK_CHOICE_DASH[0],
        ('Segmento 1', 'Segmento 1'),
        ('Segmento 2', 'Segmento 2'),
        ('Segmento 3', 'Segmento 3'),
        ('Segmento 4', 'Segmento 4'),
        ('Segmento 5', 'Segmento 5'),
        ('Segmento 6', 'Segmento 6'),
        ('Segmento 7', 'Segmento 7'),
        ('Segmento 8', 'Segmento 8'),
        ('Difusa', 'Difusa'),
        ('Subcapsular', 'Subcapsular')
    )

    CIE_11_TAGGING_CHOICES = (
        BLANK_CHOICE_DASH[0],
        ('DB90 Enfermedad infecciosa del hígado', 'DB90 Enfermedad infecciosa del hígado'),
        ('DB91 Insuficiencia hepática aguda o subaguda', 'DB91 Insuficiencia hepática aguda o subaguda'),
        ('DB92/DB94 Hepatopatía grasa', 'DB92/DB94 Hepatopatía grasa'),
        ('DB93 Fibrosis o cirrosis hepática', 'DB93 Fibrosis o cirrosis hepática'),
        ('DB95 Hepatopatía tóxica o provocada por medicamentos', 'DB95 Hepatopatía tóxica o provocada por medicamentos'),
        ('DB96 Enfermedad hepática autoinmune', 'DB96 Enfermedad hepática autoinmune'),
        ('DB97 Algunas hepatopatías inflamatorias especificadas', 'DB97 Algunas hepatopatías inflamatorias especificadas'),
        ('DB98 Trastornos vasculares del hígado', 'DB98 Trastornos vasculares del hígado'),
        ('DB99 Algunas enfermedades especificadas del hígado', 'DB99 Algunas enfermedades especificadas del hígado'),
        ('Neoplasias del hígado', 'Neoplasias del hígado'),
        ('LB20.0 Anomalías estructurales del desarrollo prenatal del hígado', 'LB20.0 Anomalías estructurales del desarrollo prenatal del hígado'),
        ('5C90 Enfermedad hepática metabólica o transportadora', '5C90 Enfermedad hepática metabólica o transportadora'),
        ('Hepatitis viral', 'Hepatitis viral'),
        ('DB9Z Enfermedades del hígado, sin especificación', 'DB9Z Enfermedades del hígado, sin especificación'),
        ('Otras', 'Otras'),
    )

    POST_CATEGORIES_CHOICE = (
        ('Abdomen', 'Abdomen'),
        ('Torax', 'Torax'),
        ('Ginecología', 'Ginecología'),
        ('Pediatría', 'Pediatría'),
        ('Neurología', 'Neurología'),
        ('Musculoesquelético', 'Musculoesquelético'),
        ('Otras', 'Otras'),
    )

    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    format = models.CharField(max_length=9, choices=FORMAT_CHOICES, null=True, blank=True)
    axial_images = models.ImageField(upload_to=images_path, null=True, blank=True)
    axial_description = models.CharField(max_length=500, blank=True, null=True)
    coronal_images = models.ImageField(upload_to=images_path, null=True, blank=True)
    category = models.CharField(max_length=20, choices=POST_CATEGORIES_CHOICE, default='Abdomen')
    coronal_description = models.CharField(max_length=500, blank=True, null=True)
    sagital_images = models.ImageField(upload_to=images_path, null=True, blank=True)
    sagital_description = models.CharField(max_length=500, blank=True, null=True)
    header_image = models.ImageField(upload_to=images_path)
    accepted_data_use = models.CharField(max_length=2, choices=USE_DATA_CHOICES, blank=True, null=True)
    cie_11_tagging = models.CharField(max_length=100, choices=CIE_11_TAGGING_CHOICES, blank=True, null=True)
    interested_region = models.CharField(max_length=100, choices=INTERESTED_REGION_CHOICES, blank=True, null=True)
    other_interested_region = models.CharField(max_length=100, blank=True, null=True)


    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(category__in=['Abdomen', 'Torax', 'Ginecología', 'Pediatría', 'Neurología', 'Musculoesquelético', 'Otras']), name='filepost_category_valid'),
            models.CheckConstraint(condition=models.Q(format__isnull=True) | models.Q(format__in=['', 'JPEG, JPG', 'DICOM']), name='filepost_format_valid'),
            models.CheckConstraint(condition=models.Q(accepted_data_use__isnull=True) | models.Q(accepted_data_use__in=['', 'Si', 'No']), name='filepost_consent_valid'),
        ]


class OriginalDicom(models.Model):
    """Private retention manifest only. No URL, public field or filename."""
    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name='retained_originals')
    object_key = models.CharField(max_length=255, unique=True)
    storage_location = models.CharField(max_length=16, choices=[('r2', 'R2'), ('filesystem', 'Private filesystem')])
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(storage_location__in=['r2', 'filesystem']), name='original_storage_valid'),
            models.CheckConstraint(condition=models.Q(sha256__regex=r'^[0-9a-f]{64}$'), name='original_sha256_valid'),
            models.CheckConstraint(condition=models.Q(byte_size__gt=0), name='original_size_positive'),
            models.CheckConstraint(condition=~models.Q(object_key=''), name='original_key_nonempty'),
        ]


class Case(models.Model):
    """Additive media extension. Post remains the case identity and URL source."""
    post = models.OneToOneField(Post, primary_key=True, on_delete=models.CASCADE, related_name='media_case')
    cover_key = models.CharField(max_length=255, blank=True)
    legacy_metadata = models.JSONField(default=dict)
    source_sha256 = models.CharField(max_length=64)
    review_state = models.CharField(max_length=24, default='legacy_unverified', choices=[('legacy_unverified', 'Legacy unverified'), ('reviewed', 'Reviewed')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(source_sha256__regex=r'^[0-9a-f]{64}$'), name='case_source_sha256_valid'),
            models.CheckConstraint(condition=models.Q(review_state__in=['legacy_unverified', 'reviewed']), name='case_review_valid'),
        ]


class Series(models.Model):
    PLANES = [('cover', 'Cover'), ('axial', 'Axial'), ('coronal', 'Coronal'), ('sagital', 'Sagittal')]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='series')
    plane = models.CharField(max_length=8, choices=PLANES)
    description = models.CharField(max_length=500, blank=True)
    order_basis = models.CharField(max_length=24, default='legacy_pk', choices=[('legacy_pk', 'Legacy PK'), ('explicit', 'Explicit position')])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['case', 'plane'], name='series_case_plane_unique'),
            models.CheckConstraint(condition=models.Q(plane__in=['cover', 'axial', 'coronal', 'sagital']), name='series_plane_valid'),
            models.CheckConstraint(condition=models.Q(order_basis__in=['legacy_pk', 'explicit']), name='series_order_basis_valid'),
        ]


class Image(models.Model):
    """Private display-object manifest. Metadata is not proof of anonymization."""
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='images')
    position = models.PositiveIntegerField()
    object_key = models.CharField(max_length=255)
    byte_size = models.PositiveBigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    storage_location = models.CharField(max_length=16, default='legacy', choices=[('legacy', 'Legacy unverified'), ('filesystem', 'Filesystem'), ('r2', 'R2')])
    verification_state = models.CharField(max_length=16, default='unverified', choices=[('unverified', 'Unverified'), ('verified', 'Verified'), ('missing', 'Missing')])
    original = models.ForeignKey(OriginalDicom, null=True, blank=True, on_delete=models.PROTECT, related_name='derived_images')
    conversion_version = models.CharField(max_length=64, blank=True)
    review_state = models.CharField(max_length=16, default='pending', choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')])
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # Scalar provenance survives replacement of legacy rows during staged edits.
    legacy_file_id = models.PositiveBigIntegerField(null=True, blank=True)
    legacy_description = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        ordering = ['position', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['series', 'position'], name='image_series_position_unique'),
            models.CheckConstraint(condition=~models.Q(object_key=''), name='image_key_nonempty'),
            models.CheckConstraint(condition=models.Q(storage_location__in=['legacy', 'filesystem', 'r2']), name='image_storage_valid'),
            models.CheckConstraint(condition=models.Q(verification_state__in=['unverified', 'verified', 'missing']), name='image_verification_valid'),
            models.CheckConstraint(condition=models.Q(sha256='') | models.Q(sha256__regex=r'^[0-9a-f]{64}$'), name='image_sha256_valid'),
            models.CheckConstraint(condition=~models.Q(verification_state='verified') | (models.Q(byte_size__gt=0) & ~models.Q(sha256='') & models.Q(byte_size__isnull=False)), name='image_verified_metadata'),
            models.CheckConstraint(condition=models.Q(review_state__in=['pending', 'approved', 'rejected']), name='image_review_valid'),
        ]
