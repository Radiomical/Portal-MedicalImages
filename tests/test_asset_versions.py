"""Version the bytes actually served, with source lookup before collectstatic."""
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.core.files.storage import FileSystemStorage
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import SimpleTestCase, TestCase, override_settings
from blog.templatetags.assets import versioned_asset


class AssetVersionTests(TestCase):
    def setUp(self):
        versioned_asset.cache_clear()

    def tearDown(self):
        versioned_asset.cache_clear()

    def test_shared_assets_use_current_content_versions(self):
        response = self.client.get('/cookies/')
        for path in ['css/style.css', 'css/clinical.css', 'js/clinical.js']:
            version = hashlib.sha256(Path(finders.find(path)).read_bytes()).hexdigest()[:12]
            self.assertContains(response, static(path) + '?v=' + version)

    @override_settings(STATIC_URL='/assets/')
    def test_alternate_static_url_is_preserved(self):
        self.assertContains(self.client.get('/cookies/'), '/assets/js/clinical.js?v=')


class CollectedAssetVersionTests(SimpleTestCase):
    def setUp(self):
        versioned_asset.cache_clear()

    def tearDown(self):
        versioned_asset.cache_clear()

    def test_collected_bytes_are_authoritative_and_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.js'
            path.write_bytes(b'collected bytes')
            storage = FileSystemStorage(location=directory, base_url='/assets/')
            with patch('blog.templatetags.assets.staticfiles_storage', storage), patch('blog.templatetags.assets.finders.find') as find:
                first = versioned_asset('example.js')
                self.assertEqual(first, '/assets/example.js?v=' + hashlib.sha256(b'collected bytes').hexdigest()[:12])
                self.assertEqual(versioned_asset('example.js'), first)
                self.assertEqual(versioned_asset.cache_info().hits, 1)
                find.assert_not_called()
                path.write_bytes(b'new deployment bytes')
                versioned_asset.cache_clear()
                self.assertNotEqual(versioned_asset('example.js'), first)

    def test_missing_asset_fails_instead_of_emitting_stale_url(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemStorage(location=directory, base_url='/assets/')
            with patch('blog.templatetags.assets.staticfiles_storage', storage), patch('blog.templatetags.assets.finders.find', return_value=None):
                with self.assertRaisesMessage(ValueError, 'Static asset not found'):
                    versioned_asset('missing.js')
