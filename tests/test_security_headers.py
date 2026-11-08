"""Response security checks use synthetic accounts and pages only."""
import pathlib
import re
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from users.models import UserProfile

class SecurityHeaderTests(TestCase):
    def test_enforced_policy_and_privacy_headers(self):
        response = self.client.get('/')
        policy = response['Content-Security-Policy']
        for directive in ("default-src 'none'", "script-src-attr 'none'", "style-src-attr 'none'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'none'", "form-action 'self'"):
            self.assertIn(directive, policy)
        for forbidden in ('unsafe-inline', 'unsafe-eval', 'https:', '*', 'report-uri'):
            self.assertNotIn(forbidden, policy)
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        self.assertEqual(response['Cross-Origin-Opener-Policy'], 'same-origin')
        self.assertIn('camera=()', response['Permissions-Policy'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_legacy_form_scripts_have_matching_unique_nonces(self):
        user = User.objects.create_user('security-fixture', password=None)
        UserProfile.objects.create(user=user)
        self.client.force_login(user)
        responses = [self.client.get('/users/profile/new-post/') for _ in range(2)]
        nonces = []
        for response in responses:
            self.assertEqual(response.status_code, 200)
            body = response.content.decode()
            scripts = re.findall(r'<script(?![^>]*\bsrc=)([^>]*)>', body)
            self.assertTrue(scripts)
            nonce = re.search(r'nonce="([^"]+)"', scripts[0]).group(1)
            self.assertIn("'nonce-" + nonce + "'", response['Content-Security-Policy'])
            self.assertTrue(all('nonce="' + nonce + '"' in attrs for attrs in scripts))
            self.assertNotRegex(body, r'<[^>]+\sstyle=')
            nonces.append(nonce)
        self.assertNotEqual(*nonces)

    @override_settings(SECURE_HSTS_SECONDS=300)
    def test_hsts_only_on_secure_requests_without_subdomain_scope(self):
        self.assertNotIn('Strict-Transport-Security', self.client.get('/'))
        self.assertEqual(self.client.get('/', secure=True)['Strict-Transport-Security'], 'max-age=300')

    def test_templates_do_not_reintroduce_inline_handlers_or_styles(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for folder in ('templates', 'users/templates', 'blog/templates'):
            for path in (root / folder).rglob('*.html'):
                with self.subTest(path=path.name):
                    self.assertNotRegex(path.read_text(), r'<[^>]+\s(?:on[a-z]+|style)=')
