"""Aggregate-only checks to run before enabling domain/email constraints."""
import json
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import Lower, Trim
from blog.models import Post
from users.models import FilePost, OriginalDicom


class Command(BaseCommand):
    help = 'Read-only aggregate domain/email checks. Does not fix, merge, delete or print accounts/cases.'

    def handle(self, *args, **options):
        result = {}
        for model, field, allowed in [
            (Post, 'category', [v for v, _ in Post.POST_CATEGORIES_CHOICE]),
            (Post, 'medical_findings', [''] + [v for v, _ in Post.MEDICAL_FINDINGS_CHOICES]),
            (FilePost, 'category', [v for v, _ in FilePost.POST_CATEGORIES_CHOICE]),
            (FilePost, 'format', ['', 'JPEG, JPG', 'DICOM']),
            (FilePost, 'accepted_data_use', ['', 'Si', 'No']),
            (OriginalDicom, 'storage_location', ['r2', 'filesystem']),
        ]:
            result[model._meta.label + '.' + field + '.invalid'] = model.objects.exclude(**{field + '__in': allowed}).exclude(**{field + '__isnull': True}).count()
        result['OriginalDicom.sha256.invalid'] = OriginalDicom.objects.exclude(sha256__regex=r'^[0-9a-f]{64}$').count()
        result['OriginalDicom.byte_size.invalid'] = OriginalDicom.objects.filter(byte_size=0).count()
        result['OriginalDicom.object_key.invalid'] = OriginalDicom.objects.filter(object_key='').count()
        result['normalized_email_collision_groups'] = (User.objects.annotate(normalized=Lower(Trim('email'))).exclude(normalized='').values('normalized').annotate(total=Count('pk')).filter(total__gt=1).count())
        self.stdout.write(json.dumps(result, sort_keys=True))
