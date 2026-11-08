"""Regression coverage using only synthetic accounts and images."""
import os
import tempfile
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from blog.models import Post
from users.models import FilePost, UserProfile
from portal.settings import env_bool
from users.helpers.tokens import account_activation_token, reset_password_token

class SettingsTests(SimpleTestCase):
    def test_false_text_is_false(self):
        for value in ["False", "false", "0", "no", ""]:
            with self.subTest(value=value), patch.dict(os.environ, {"TEST_FLAG": value}):
                self.assertFalse(env_bool("TEST_FLAG"))
    def test_true_text_is_true(self):
        with patch.dict(os.environ, {"TEST_FLAG": "true"}):
            self.assertTrue(env_bool("TEST_FLAG"))
    def test_invalid_flag_fails_closed(self):
        with patch.dict(os.environ, {"TEST_FLAG": "invalid"}):
            with self.assertRaises(ImproperlyConfigured):
                env_bool("TEST_FLAG")

class PortalSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sample", "sample@example.invalid", "Synthetic-Test-3281!")
        UserProfile.objects.create(user=self.user)
        self.post = Post.objects.create(title="Synthetic fixture", content="Synthetic content", author=self.user)
        FilePost.objects.create(post=self.post, header_image="synthetic/cover.jpg")
    def test_public_routes(self):
        for route in ["/", "/all-blogs/", "/search/?q=Synthetic", "/users/login/", "/users/signup/", "/users/reset-password/"]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)
    def test_detail(self):
        self.assertEqual(self.client.get(reverse("blog:blog_page", args=[self.post.title, self.post.pk])).status_code, 200)
    def test_detail_without_profile(self):
        UserProfile.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.get(reverse("blog:blog_page", args=[self.post.title, self.post.pk])).status_code, 200)
    def test_profile_and_upload_require_login(self):
        for path in ["/users/profile/", "/users/profile/new-post/"]:
            self.assertEqual(self.client.get(path).status_code, 302)
    def test_login_profile_and_logout(self):
        self.client.post("/users/login/", {"email": self.user.email, "password": "Synthetic-Test-3281!"})
        self.assertEqual(self.client.get("/users/profile/").status_code, 200)
        self.assertEqual(self.client.get("/users/logout/").status_code, 302)
    def test_edit_requires_owner(self):
        other = User.objects.create_user("other", "other@example.invalid", "Synthetic-Test-3281!")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("blog:edit_blog", args=[self.post.pk])).status_code, 302)
    def test_api_requires_authentication(self):
        self.assertEqual(self.client.get("/api/get/posts/").status_code, 401)
    def test_activation_token_expires_after_activation(self):
        self.user.is_active = False
        self.user.save()
        token = account_activation_token.make_token(self.user)
        self.assertTrue(account_activation_token.check_token(self.user, token))
        self.user.is_active = True
        self.assertFalse(account_activation_token.check_token(self.user, token))
    def test_reset_token_expires_after_password_change(self):
        token = reset_password_token.make_token(self.user)
        self.assertTrue(reset_password_token.check_token(self.user, token))
        self.user.set_password("Synthetic-Replacement-3952!")
        self.assertFalse(reset_password_token.check_token(self.user, token))

class ConfigurationIsolationTests(SimpleTestCase):
    def test_production_defaults_do_not_enable_debug(self):
        import subprocess, sys
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "portal.settings", "SECRET_KEY": "synthetic-process-only-test-key-0123456789", "DEBUG": "False", "DB_ENGINE": "sqlite", "SECURE_COOKIES": "true", "SECURE_SSL_REDIRECT": "true"}
        result = subprocess.run([sys.executable, "-c", "from django.conf import settings; assert settings.DEBUG is False; assert settings.SESSION_COOKIE_SECURE; assert settings.CSRF_COOKIE_SECURE; assert settings.SECURE_SSL_REDIRECT"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
    def test_missing_secret_key_refuses_startup(self):
        import subprocess, sys
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "portal.settings", "SECRET_KEY": ""}
        result = subprocess.run([sys.executable, "-c", "from django.conf import settings; print(settings.DEBUG)"], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY is required", result.stderr)

class SyntheticUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("synthetic-uploader", "uploader@example.invalid", "Synthetic-Test-3281!")
        UserProfile.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)

    def data(self, image_format, cover):
        return {"title": "Synthetic upload", "content": "Generated fixture, not a patient", "category": "Abdomen", "medical_findings": "Moderada", "format": image_format, "accepted_data_use": "No", "header_image": cover}

    def test_jpeg_upload_uses_isolated_media(self):
        import io
        from pathlib import Path
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        content = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(content, "JPEG")
        cover = SimpleUploadedFile("synthetic.jpg", content.getvalue(), content_type="image/jpeg")
        response = self.client.post("/users/profile/new-post/", self.data("JPEG, JPG", cover))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["error"])
        asset = FilePost.objects.get()
        self.assertTrue(Path(asset.header_image.path).is_relative_to(self.media.name))
        self.assertTrue(Path(asset.header_image.path).is_file())

    def test_dicom_conversion_honors_media_root(self):
        import io
        from pathlib import Path
        from pydicom.dataset import FileDataset, FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
        from django.core.files.uploadedfile import SimpleUploadedFile
        meta = FileMetaDataset()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        dataset = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        dataset.SOPClassUID = meta.MediaStorageSOPClassUID
        dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        dataset.Rows = dataset.Columns = 8
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        dataset.BitsAllocated = dataset.BitsStored = 8
        dataset.HighBit = 7
        dataset.PixelRepresentation = 0
        dataset.PixelData = b"\x40" * 64
        content = io.BytesIO()
        dataset.save_as(content, enforce_file_format=True)
        cover = SimpleUploadedFile("synthetic.dcm", content.getvalue(), content_type="application/dicom")
        response = self.client.post("/users/profile/new-post/", self.data("DICOM", cover))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["error"])
        asset = FilePost.objects.get()
        self.assertTrue(Path(asset.header_image.path).is_relative_to(self.media.name))
        self.assertTrue(Path(asset.header_image.path).is_file())
        self.assertEqual(list(Path(self.media.name).rglob("*.dcm")), [])

class UploadCompatibilityTests(SimpleTestCase):
    def test_default_file_count_preserves_series_capacity(self):
        import subprocess, sys
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "portal.settings", "SECRET_KEY": "synthetic-process-only-test-key-0123456789", "MAX_UPLOAD_FILES": ""}
        result = subprocess.run([sys.executable, "-c", "from django.conf import settings; assert settings.DATA_UPLOAD_MAX_NUMBER_FILES is None"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

class RecoveredBaselineTests(SimpleTestCase):
    def test_branding_assets_are_available(self):
        from django.contrib.staticfiles import finders
        for name in ["css/style.css", "js/script.js", "images/logo.png", "images/logonrecred1.png", "images/favico.ico"]:
            with self.subTest(name=name):
                self.assertIsNotNone(finders.find(name))

    def test_country_choices_keep_existing_labels(self):
        from users.models import COUNTRY_CHOICES
        from users.forms import UserUpdateForm
        self.assertIn(("Turkey", "Turkey"), COUNTRY_CHOICES)
        self.assertIn(("Turkey", "Turkey"), UserUpdateForm().fields["user_country"].choices)

class HistoricalChoiceTests(SimpleTestCase):
    def test_country_snapshot_matches_migration(self):
        import importlib
        from users.countries import COUNTRY_CHOICES
        historical = importlib.import_module("users.migrations.0037_userprofile")
        field = dict(historical.Migration.operations[0].fields)["country"]
        self.assertEqual(COUNTRY_CHOICES, list(field.choices))

class PreviewRestrictionTests(SimpleTestCase):
    def test_preview_blocks_writes_and_private_routes(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        from portal.staging import ReadOnlyPreviewMiddleware
        middleware = ReadOnlyPreviewMiddleware(lambda request: HttpResponse('Synthetic'))
        factory = RequestFactory()
        self.assertEqual(middleware(factory.get('/')).status_code, 200)
        self.assertEqual(middleware(factory.post('/users/login/', {})).status_code, 403)
        for path in ['/admin/', '/xxx/', '/api/get/posts/', '/users/signup/', '/users/profile/', '/users/reset-password/', '/users/activate/anything/']:
            with self.subTest(path=path):
                self.assertEqual(middleware(factory.get(path)).status_code, 404)
