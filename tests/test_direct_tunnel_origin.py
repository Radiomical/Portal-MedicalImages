"""Synthetic direct-origin behavior with a trusted HTTPS connector, no Nginx."""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=True,
                   SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
                   SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
                   ALLOWED_HOSTS=['portal.example.test'],
                   CSRF_TRUSTED_ORIGINS=['https://portal.example.test'])
class DirectTunnelOriginTests(TestCase):
    def client_with_scheme(self, scheme='https'):
        return Client(enforce_csrf_checks=True, HTTP_HOST='portal.example.test',
                      HTTP_X_FORWARDED_PROTO=scheme)

    def test_forwarded_https_does_not_loop_and_has_security_headers(self):
        response = self.client_with_scheme().get('/cookies/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Strict-Transport-Security'], 'max-age=300')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        self.assertIn('camera=()', response['Permissions-Policy'])
        self.assertIn("default-src 'none'", response['Content-Security-Policy'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertContains(response, '/static/js/clinical.js?v=')

    def test_http_origin_is_redirected_to_public_https_host(self):
        response = self.client_with_scheme('http').get('/cookies/?a=1')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://portal.example.test/cookies/?a=1')

    def test_login_csrf_and_secure_session_work_without_nginx(self):
        User.objects.create_user('synthetic-connector', email='connector@example.invalid', password='synthetic-passphrase-only')
        client = self.client_with_scheme()
        self.assertEqual(client.get('/users/login/').status_code, 200)
        token = client.cookies['csrftoken'].value
        self.assertTrue(client.cookies['csrftoken']['secure'])
        payload = {'email': 'connector@example.invalid', 'password': 'synthetic-passphrase-only'}
        self.assertEqual(client.post('/users/login/', payload).status_code, 403)
        response = client.post('/users/login/', payload, HTTP_X_CSRFTOKEN=token,
                               HTTP_ORIGIN='https://portal.example.test')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/users/profile/')
        self.assertTrue(client.cookies['sessionid']['secure'])
        self.assertEqual(client.get('/users/profile/').status_code, 200)

    def test_foreign_origin_is_not_authorized_by_forwarded_https(self):
        client = self.client_with_scheme()
        client.get('/users/login/')
        response = client.post('/users/login/', {}, HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value,
                               HTTP_ORIGIN='https://untrusted.example.test')
        self.assertEqual(response.status_code, 403)

    def test_direct_wsgi_does_not_serve_original_dicom_or_old_media(self):
        self.assertEqual(self.client_with_scheme().get('/media/synthetic.dcm').status_code, 404)
