import os
import subprocess
import sys
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.http import HttpResponse
from django.urls import reverse


class AdminRouteTests(SimpleTestCase):
    def test_default_admin_resolves(self):
        self.assertEqual(reverse('admin:index'), '/xxx/')

    def test_configured_admin_resolves_in_fresh_process(self):
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'portal.settings',
               'SECRET_KEY': 'synthetic-admin-route-test-key-0123456789',
               'DB_ENGINE': 'sqlite', 'ADMIN_URL_PATH': 'control-panel/'}
        result = subprocess.run([sys.executable, '-c',
            "import django;django.setup();from django.urls import reverse;assert reverse('admin:index') == '/control-panel/'"],
            env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_paths_fail_closed(self):
        for value in ['', '/', 'nested/path/', '../admin/', 'admin', 'admin/?x', '*', 'users/', 'api/', 'static/', 'media/', 'search/']:
            env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'portal.settings',
                   'SECRET_KEY': 'synthetic-admin-route-test-key-0123456789',
                   'ADMIN_URL_PATH': value}
            result = subprocess.run([sys.executable, '-c',
                'from django.conf import settings;print(settings.ADMIN_URL_PATH)'],
                env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, value)
            self.assertIn('ImproperlyConfigured', result.stderr)

    @override_settings(ADMIN_URL_PATH='control-panel/')
    def test_preview_blocks_configured_root_and_descendants(self):
        from portal.staging import ReadOnlyPreviewMiddleware
        middleware = ReadOnlyPreviewMiddleware(lambda request: HttpResponse('Synthetic'))
        for path in ['/control-panel', '/control-panel/', '/control-panel/login/']:
            self.assertEqual(middleware(RequestFactory().get(path)).status_code, 404)
        self.assertEqual(middleware(RequestFactory().get('/control-panel-public/')).status_code, 200)
