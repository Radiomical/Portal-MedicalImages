"""Keep HTML URLs in sync with content changes, including CDN/browser caches."""
import hashlib
from pathlib import Path
from django.test import TestCase


class AssetVersionTests(TestCase):
    def test_shared_assets_use_current_content_versions(self):
        root = Path(__file__).resolve().parents[1]
        response = self.client.get('/cookies/')
        for path in ['css/style.css', 'css/clinical.css', 'js/clinical.js']:
            version = hashlib.sha256((root / 'static-src' / path).read_bytes()).hexdigest()[:12]
            self.assertContains(response, '/static/' + path + '?v=' + version)
