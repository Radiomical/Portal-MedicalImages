from django.db import models
from django.contrib.auth.models import User

class Post(models.Model):
    POST_CATEGORIES_CHOICE = (
        ('Abdomen', 'Abdomen'),
        ('Torax', 'Torax'),
        ('Ginecología', 'Ginecología'),
        ('Pediatría', 'Pediatría'),
        ('Neurología', 'Neurología'),
        ('Musculoesquelético', 'Musculoesquelético'),
        ('Otras', 'Otras'),
    )

    MEDICAL_FINDINGS_CHOICES = (
        ('Alta (confirmación anatomopatológica/quirúrgica)', 'Alta (confirmación anatomopatológica/quirúrgica)'),
        ('Moderada', 'Moderada'),
        ('Baja', 'Baja'),
    )

    title = models.CharField(max_length=100)
    content = models.TextField()
    date_posted = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.CharField(max_length=20, choices=POST_CATEGORIES_CHOICE, default='Abdomen')
    fisiopathology = models.TextField(blank=True, null=True)
    clinical_case = models.TextField(blank=True, null=True)
    clinical_signs = models.TextField(blank=True, null=True)
    doppler = models.TextField(blank=True, null=True)
    medical_findings = models.CharField(max_length=100, choices=MEDICAL_FINDINGS_CHOICES, default='Alta (confirmación anatomopatológica/quirúrgica)')
    preparation = models.TextField(blank=True, null=True)
    sequential = models.TextField(blank=True, null=True)
    pediatrics = models.TextField(blank=True, null=True)
    medical_report = models.TextField(blank=True, null=True)
    seram_link = models.URLField(blank=True, null=True)
    radiopedia_link = models.URLField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._meta.get_field('doppler').blank = not self.is_torax()

    def is_torax(self):
        return self.category == 'Torax'