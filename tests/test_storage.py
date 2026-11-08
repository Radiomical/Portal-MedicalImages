"""No network, credentials or real images are used by these tests."""
from unittest.mock import Mock, patch
from django.core.files.base import ContentFile
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.test import SimpleTestCase, override_settings
from botocore.exceptions import ClientError
from portal.storage import PrivateImageStorage, quarantine_dicom

@override_settings(R2_IMAGE_BUCKET='synthetic-images', R2_DICOM_BUCKET='synthetic-originals', R2_SIGNED_URL_SECONDS=300)
class StorageTests(SimpleTestCase):
    def storage(self):
        storage = PrivateImageStorage()
        storage.client = Mock()
        return storage

    def test_signed_url_has_short_expiry_and_no_public_acl(self):
        s = self.storage()
        s.url('synthetic/cover.jpg')
        s.client.generate_presigned_url.assert_called_once_with('get_object', Params={'Bucket':'synthetic-images','Key':'synthetic/cover.jpg'}, ExpiresIn=300)
        s._save('synthetic/cover.jpg', ContentFile(b'synthetic'))
        self.assertNotIn('ACL', s.client.upload_fileobj.call_args.kwargs['ExtraArgs'])

    def test_dicom_and_traversal_cannot_be_signed_or_saved(self):
        for name in ['original.dcm', 'original.DCM', '../cover.jpg', '/cover.jpg', 'a//cover.jpg', 'a\\cover.jpg', 'cover.html']:
            with self.subTest(name=name):
                s = self.storage()
                with self.assertRaises(SuspiciousFileOperation): s.url(name)
                with self.assertRaises(SuspiciousFileOperation): s._save(name, ContentFile(b'synthetic'))
                s.client.generate_presigned_url.assert_not_called()

    def test_only_404_is_missing(self):
        s = self.storage()
        s.client.head_object.side_effect = ClientError({'Error':{'Code':'404'},'ResponseMetadata':{'HTTPStatusCode':404}},'HeadObject')
        self.assertFalse(s.exists('cover.jpg'))
        s.client.head_object.side_effect = ClientError({'Error':{'Code':'403'},'ResponseMetadata':{'HTTPStatusCode':403}},'HeadObject')
        with self.assertRaises(ClientError): s.exists('cover.jpg')

    @override_settings(R2_SIGNED_URL_SECONDS=86400)
    def test_long_expiry_refused(self):
        with self.assertRaises(ImproperlyConfigured): self.storage().url('cover.jpg')

    @override_settings(R2_DICOM_BUCKET='synthetic-images')
    def test_same_bucket_quarantine_refused(self):
        with self.assertRaises(ImproperlyConfigured): quarantine_dicom(ContentFile(b'synthetic'),'synthetic/original.dcm')

    def test_quarantine_has_no_signed_url(self):
        s = self.storage()
        with patch('portal.storage.PrivateImageStorage', return_value=s):
            key = quarantine_dicom(ContentFile(b'synthetic'), 'synthetic/original.dcm')
        self.assertEqual(key, 'synthetic/original.dcm')
        self.assertEqual(s.client.upload_fileobj.call_args.args[1], 'synthetic-originals')
        s.client.generate_presigned_url.assert_not_called()

    @override_settings(R2_ENDPOINT_URL='http://untrusted.invalid', R2_ACCESS_KEY_ID='synthetic', R2_SECRET_ACCESS_KEY='synthetic')
    def test_untrusted_endpoint_refused_before_network(self):
        with patch('portal.storage.boto3.client') as client:
            with self.assertRaises(ImproperlyConfigured): PrivateImageStorage().client
            client.assert_not_called()
