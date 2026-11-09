"""Synthetic configuration tests; never authenticate or send real mail."""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.core import mail
from portal.email_config import email_configuration


class EmailConfigurationTests(SimpleTestCase):
    def test_default_remains_console_and_custom_mode_remains_compatible(self):
        config = email_configuration({})
        self.assertEqual(config['EMAIL_PROVIDER'], 'custom')
        self.assertEqual(config['EMAIL_BACKEND'], 'django.core.mail.backends.console.EmailBackend')
        config = email_configuration({'EMAIL_HOST': 'smtp.example.test', 'EMAIL_HOST_USER': 'fixture',
                                      'EMAIL_PORT': '2525', 'EMAIL_USE_TLS': 'false'})
        self.assertEqual(config['EMAIL_HOST'], 'smtp.example.test')
        self.assertEqual(config['EMAIL_PORT'], 2525)
        self.assertFalse(config['EMAIL_USE_TLS'])

    def test_custom_tls_preserves_previous_env_bool_semantics(self):
        for value in ('true', 'TRUE', '1', 'yes', 'YES'):
            with self.subTest(value=value):
                self.assertTrue(email_configuration({'EMAIL_USE_TLS': value})['EMAIL_USE_TLS'])
        for value in ('false', 'FALSE', '0', 'no', ''):
            with self.subTest(value=value):
                self.assertFalse(email_configuration({'EMAIL_USE_TLS': value})['EMAIL_USE_TLS'])
        for value in ('on', 'off', 'True ', 'invalid'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                email_configuration({'EMAIL_USE_TLS': value})
        self.assertTrue(email_configuration({})['EMAIL_USE_TLS'])
        self.assertFalse(email_configuration({})['EMAIL_USE_SSL'])

    def test_custom_port_has_clear_error_for_invalid_values(self):
        for value in ('', 'invalid', '0', '65536'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                email_configuration({'EMAIL_PORT': value})

    def test_resend_pins_tls_and_never_silently_uses_console(self):
        config = email_configuration({'EMAIL_PROVIDER': 'resend', 'DEFAULT_FROM_EMAIL': 'no-reply@notifications.example.test',
                                      'EMAIL_HOST_PASSWORD': 'synthetic-fixture-only',
                                      'EMAIL_BACKEND': 'django.core.mail.backends.console.EmailBackend',
                                      'EMAIL_HOST': 'untrusted.invalid', 'EMAIL_USE_TLS': 'false'})
        self.assertEqual(config['EMAIL_BACKEND'], 'django.core.mail.backends.smtp.EmailBackend')
        self.assertEqual(config['EMAIL_HOST'], 'smtp.resend.com')
        self.assertEqual(config['EMAIL_HOST_USER'], 'resend')
        self.assertEqual(config['EMAIL_PORT'], 587)
        self.assertTrue(config['EMAIL_USE_TLS'])
        self.assertFalse(config['EMAIL_USE_SSL'])
        self.assertEqual(config['EMAIL_TIMEOUT'], 20)
        self.assertEqual(config['DEFAULT_FROM_EMAIL'], 'no-reply@notifications.example.test')

    def test_missing_invalid_sender_or_secret_fails_closed(self):
        base = {'EMAIL_PROVIDER': 'resend', 'EMAIL_HOST_PASSWORD': 'synthetic-fixture-only',
                'DEFAULT_FROM_EMAIL': 'no-reply@notifications.example.test'}
        for change in ({'EMAIL_HOST_PASSWORD': ''}, {'DEFAULT_FROM_EMAIL': ''},
                       {'DEFAULT_FROM_EMAIL': 'invalid'}, {'EMAIL_PROVIDER': 'unknown'}):
            with self.subTest(change=change), self.assertRaises(ImproperlyConfigured):
                email_configuration(base | change)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                       DEFAULT_FROM_EMAIL='no-reply@notifications.example.test')
    def test_sending_from_configured_identity_adds_no_reply_to(self):
        from django.conf import settings
        mail.send_mail('Synthetic fixture', 'Generated test only.', settings.DEFAULT_FROM_EMAIL,
                       ['recipient@example.test'], fail_silently=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'no-reply@notifications.example.test')
        self.assertEqual(mail.outbox[0].reply_to, [])
        self.assertNotIn('Reply-To', mail.outbox[0].message())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   DEFAULT_FROM_EMAIL='no-reply@notifications.example.test')
class TransactionalMailIdentityTests(TestCase):
    def test_signup_and_reset_use_configured_sender_without_reply_to(self):
        response = self.client.post('/users/signup/', {'username': 'mail-fixture',
            'email': 'recipient@example.test', 'password1': 'Synthetic-Fixture-937!',
            'password2': 'Synthetic-Fixture-937!'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'no-reply@notifications.example.test')
        self.assertEqual(mail.outbox[0].reply_to, [])
        self.assertEqual(mail.outbox[0].to, ['recipient@example.test'])
        from django.contrib.auth.models import User
        user = User.objects.get(username='mail-fixture')
        user.is_active = True
        user.save()
        response = self.client.post('/users/reset-password/', {'email': user.email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].from_email, 'no-reply@notifications.example.test')
        self.assertEqual(mail.outbox[1].reply_to, [])
        self.assertEqual(mail.outbox[1].to, ['recipient@example.test'])
