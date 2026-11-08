"""Seed a public preview with generated, explicitly non-clinical content."""
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw
from blog.models import Post
from users.models import FilePost, UserProfile

class Command(BaseCommand):
    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != 'portal.settings_staging':
            raise CommandError('Only the isolated staging settings may seed preview data')
        if User.objects.exists() or Post.objects.exists():
            raise CommandError('Preview seed requires an empty database')
        path = Path(settings.MEDIA_ROOT) / 'synthetic' / 'preview.jpg'
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new('RGB', (1000, 700), '#172a2d')
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 100, 920, 600), outline='#8ad4b8', width=4)
        draw.text((120, 280), 'SYNTHETIC PREVIEW - NOT A PATIENT IMAGE', fill='white', font_size=26)
        image.save(path, 'JPEG')
        try:
            with transaction.atomic():
                user = User.objects.create_user('synthetic-author', 'synthetic@example.invalid', password=None)
                UserProfile.objects.create(user=user)
                post = Post.objects.create(title='Synthetic demonstration', content='Synthetic demonstration only. No patient data or diagnostic image.', author=user, category='Abdomen', clinical_case='Fictional case for interface testing only.')
                FilePost.objects.create(post=post, header_image='synthetic/preview.jpg', axial_images='synthetic/preview.jpg', accepted_data_use='No')
        except Exception:
            path.unlink(missing_ok=True)
            raise
        self.stdout.write('Synthetic preview seeded. No usable account password was created.')
