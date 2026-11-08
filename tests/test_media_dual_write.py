import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from blog.models import Post
from users.models import Case, FilePost, Image, OriginalDicom
from users.case_media import backfill_case, projection, verify_case
from tests.test_upload_storage import jpeg, dicom


class MediaDualWriteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dual-synthetic')
        self.client.force_login(self.user)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = override_settings(MEDIA_ROOT=self.temp.name+'/media', PRIVATE_DICOM_ROOT=self.temp.name+'/private', CASE_MEDIA_DUAL_WRITE=True)
        settings.enable()
        self.addCleanup(settings.disable)

    def data(self, kind='JPEG, JPG', retain='No'):
        return {'title': 'Synthetic dual case', 'content': 'Generated only', 'category': 'Abdomen', 'medical_findings': 'Sin evaluar', 'format': kind, 'accepted_data_use': retain, 'header_image': dicom() if kind=='DICOM' else jpeg()}

    def test_upload_captures_sent_byte_metadata_and_preserves_legacy(self):
        data = self.data()
        data['axial_image'] = [jpeg('synthetic-a.jpg'), jpeg('synthetic-b.jpg')]
        response = self.client.post('/users/profile/new-post/', data)
        self.assertFalse(response.context['error'])
        case = Case.objects.get()
        self.assertFalse(case.projection_stale)
        verify_case(case, projection(case.post))
        self.assertEqual(Image.objects.count(), 3)
        for image in Image.objects.all():
            raw = (Path(self.temp.name)/'media'/image.object_key).read_bytes()
            self.assertEqual(image.sha256, hashlib.sha256(raw).hexdigest())
            self.assertEqual(image.byte_size, len(raw))
            self.assertEqual(image.verification_state, 'unverified')
            self.assertEqual(image.review_state, 'pending')
        self.assertEqual(FilePost.objects.count(), 2)

    @override_settings(DICOM_RETENTION_ENABLED=True)
    def test_dicom_lineage_is_known_without_exposing_original_url(self):
        response = self.client.post('/users/profile/new-post/', self.data('DICOM','Si'))
        self.assertFalse(response.context['error'])
        image = Image.objects.get()
        self.assertEqual(image.original_id, OriginalDicom.objects.get().pk)
        self.assertEqual(image.conversion_version, 'educational-jpeg-v1')
        self.assertEqual(image.verification_state, 'unverified')
        self.assertFalse(hasattr(image.original, 'url'))

    def test_edit_replaces_db_projection_and_preserves_case_identity(self):
        self.client.post('/users/profile/new-post/', self.data())
        case = Case.objects.get()
        old_key = Image.objects.get().object_key
        response = self.client.post(reverse('blog:edit_blog', args=[case.pk]), self.data())
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertFalse(case.projection_stale)
        verify_case(case, projection(case.post))
        self.assertFalse(Image.objects.filter(object_key=old_key).exists())
        self.assertTrue((Path(self.temp.name)/'media'/old_key).exists())  # No object deletion.

    def test_projection_failure_rolls_back_legacy_case_changes(self):
        self.client.post('/users/profile/new-post/', self.data())
        case = Case.objects.get()
        old_key = Image.objects.get().object_key
        data = self.data()
        data['title'] = 'Should roll back'
        with patch('blog.views.sync_uploaded_case', side_effect=RuntimeError('Synthetic DB error')):
            response = self.client.post(reverse('blog:edit_blog', args=[case.pk]), data)
        self.assertTrue(response.context['error'])
        case.refresh_from_db()
        self.assertEqual(case.post.title, 'Synthetic dual case')
        self.assertEqual(Image.objects.get().object_key, old_key)
        self.assertFalse(case.projection_stale)

    def test_admin_style_mutations_mark_stale(self):
        self.client.post('/users/profile/new-post/', self.data())
        case = Case.objects.get()
        legacy = FilePost.objects.get()
        legacy.header_image = 'synthetic/changed.jpg'
        legacy.save()
        case.refresh_from_db()
        self.assertTrue(case.projection_stale)
        with self.assertRaises(ValueError):
            backfill_case(case.pk)

    @override_settings(CASE_MEDIA_DUAL_WRITE=False)
    def test_default_off_keeps_legacy_only_upload(self):
        self.client.post('/users/profile/new-post/', self.data())
        self.assertTrue(FilePost.objects.exists())
        self.assertFalse(Case.objects.exists())

    def test_admin_style_move_invalidates_both_cases(self):
        self.client.post('/users/profile/new-post/', self.data())
        old_case = Case.objects.get()
        other = Post.objects.create(title='Generated other case', content='Synthetic', author=self.user)
        backfill_case(other.pk)
        legacy = FilePost.objects.get()
        legacy.post = other
        legacy.save()
        self.assertTrue(Case.objects.get(pk=old_case.pk).projection_stale)
        self.assertTrue(Case.objects.get(pk=other.pk).projection_stale)
