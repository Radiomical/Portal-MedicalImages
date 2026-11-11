"""Opt-in public-image caching, with synthetic keys and no network calls."""
from unittest.mock import Mock, patch
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings
from portal.media_config import validate_public_image_origin, image_csp_origins
from portal.storage import PrivateImageStorage, quarantine_dicom


@override_settings(R2_IMAGE_BUCKET='synthetic-images', R2_DICOM_BUCKET='synthetic-originals',
                   R2_IMAGE_PUBLIC_BASE_URL='https://media.example.test', R2_SIGNED_URL_SECONDS=300)
class PublicImageCacheTests(SimpleTestCase):
    def storage(self):
        storage = PrivateImageStorage()
        storage.client = Mock()
        return storage

    def test_public_urls_are_stable_encoded_and_network_free(self):
        storage = self.storage()
        key = 'synthetic/cut #1?%café.jpg'
        expected = 'https://media.example.test/synthetic/cut%20%231%3F%25caf%C3%A9.jpg'
        self.assertEqual(storage.url(key), expected)
        self.assertEqual(storage.url(key), expected)
        self.assertEqual(storage.client.mock_calls, [])

    def test_public_url_does_not_initialize_s3_client(self):
        with patch('portal.storage.boto3.client') as client:
            self.assertEqual(PrivateImageStorage().url('images/fixture.jpg'),
                             'https://media.example.test/images/fixture.jpg')
            client.assert_not_called()

    def test_public_writes_have_immutable_header_and_stay_create_only(self):
        storage = self.storage()
        storage._save('images/fixture.jpg', ContentFile(b'synthetic'))
        args = storage.client.put_object.call_args.kwargs
        self.assertEqual(args['CacheControl'], 'public, max-age=31536000, immutable')
        self.assertEqual(args['IfNoneMatch'], '*')
        self.assertNotIn('ACL', args)

    @override_settings(R2_IMAGE_PUBLIC_BASE_URL='')
    def test_empty_setting_restores_signed_urls_and_private_new_writes(self):
        storage = self.storage()
        storage.url('images/fixture.jpg')
        storage.client.generate_presigned_url.assert_called_once_with(
            'get_object', Params={'Bucket': 'synthetic-images', 'Key': 'images/fixture.jpg'}, ExpiresIn=300)
        storage._save('images/fixture.jpg', ContentFile(b'synthetic'))
        self.assertEqual(storage.client.put_object.call_args.kwargs['CacheControl'], 'private, max-age=60')

    def test_originals_never_get_public_urls_or_cache_headers(self):
        storage = self.storage()
        for name in ('original.dcm', 'original.DCM', '../cover.jpg', '/cover.jpg', 'a//cover.jpg', 'a\\cover.jpg', 'x.html'):
            with self.subTest(name=name), self.assertRaises(SuspiciousFileOperation):
                storage.url(name)
        with patch('portal.storage.PrivateImageStorage', return_value=storage):
            quarantine_dicom(ContentFile(b'synthetic'), 'synthetic/original.dcm')
        args = storage.client.put_object.call_args.kwargs
        self.assertEqual(args['Bucket'], 'synthetic-originals')
        self.assertEqual(args['CacheControl'], 'no-store')
        self.assertEqual(args['IfNoneMatch'], '*')
        storage.client.generate_presigned_url.assert_not_called()

    @override_settings(R2_DICOM_BUCKET='synthetic-images')
    def test_shared_bucket_refused_in_public_mode(self):
        storage = self.storage()
        with self.assertRaises(ImproperlyConfigured):
            storage.url('cover.jpg')
        with self.assertRaises(ImproperlyConfigured):
            storage._save('cover.jpg', ContentFile(b'synthetic'))
        self.assertEqual(storage.client.mock_calls, [])

    def test_origin_validation_and_exact_image_csp(self):
        self.assertEqual(validate_public_image_origin('https://media.example.test/'), 'https://media.example.test')
        self.assertEqual(validate_public_image_origin(''), '')
        origins = image_csp_origins('https://synthetic.r2.cloudflarestorage.com',
                                    'synthetic-images', 'https://media.example.test')
        self.assertEqual(origins[-1], 'https://media.example.test')
        self.assertNotIn('*', origins)
        self.assertNotIn('https:', origins)
        self.assertNotIn('https://media.example.test', image_csp_origins('', '', ''))
        for value in ('http://media.example.test', 'https://media.example.test/path',
                      'https://media.example.test?token=x', 'https://media.example.test#',
                      'https://' + 'user:' + 'synthetic@media.example.test', 'https://media.example.test:443',
                      'https://*.example.test', 'https://127.0.0.1', 'https://localhost',
                      'https://bucket.r2.dev', 'https://synthetic.r2.cloudflarestorage.com',
                      ' https://media.example.test', 'https://media.example.test?',
                      'https://media.example.test/\n', 'https://media.\nexample.test', 'https://['):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                validate_public_image_origin(value)

    def test_real_settings_allow_public_image_reads_but_not_scripts_or_private_origins(self):
        import json
        import os
        import subprocess
        import sys
        env = dict(os.environ, DJANGO_SETTINGS_MODULE='portal.settings_test', MEDIA_STORAGE='r2',
                   R2_IMAGE_BUCKET='synthetic-images', R2_DICOM_BUCKET='synthetic-originals',
                   R2_IMAGE_PUBLIC_BASE_URL='https://media.example.test',
                   R2_ENDPOINT_URL='https://synthetic.eu.r2.cloudflarestorage.com')
        code = 'import django,json;django.setup();from django.conf import settings;print(json.dumps(settings.SECURE_CSP))'
        result = subprocess.run([sys.executable, '-c', code], env=env, text=True, capture_output=True, check=True)
        policy = json.loads(result.stdout)
        self.assertIn('https://media.example.test', policy['img-src'])
        self.assertNotIn('https://media.example.test', policy['script-src'])
        self.assertIn('https://media.example.test', policy['connect-src'])
        self.assertNotIn('https://synthetic.eu.r2.cloudflarestorage.com', policy['connect-src'])
        self.assertNotIn('https://synthetic-originals.synthetic.eu.r2.cloudflarestorage.com', policy['connect-src'])
        for overrides in ({'R2_DICOM_BUCKET': 'synthetic-images'}, {'MEDIA_STORAGE': 'filesystem'},
                          {'R2_DICOM_BUCKET': ''}):
            with self.subTest(overrides=overrides):
                invalid = subprocess.run([sys.executable, '-c', code], env=env | overrides,
                                         text=True, capture_output=True)
                self.assertNotEqual(invalid.returncode, 0)
                self.assertIn('ImproperlyConfigured', invalid.stderr)
