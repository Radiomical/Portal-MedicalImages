from django.test import TestCase


class CookieNoticeTests(TestCase):
    def test_cookie_notice_uses_shared_layout_and_keeps_legal_copy(self):
        response = self.client.get('/cookies/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base.html')
        self.assertContains(response, 'class="clinical"')
        self.assertContains(response, 'cookie-notice')
        self.assertContains(response, 'css/clinical.css')
        self.assertContains(response, '¿Qué son las cookies?')
        self.assertContains(response, 'Google Adsense')
        self.assertContains(response, '<main ', count=1)
        self.assertContains(response, '<!doctype html>', count=1)
