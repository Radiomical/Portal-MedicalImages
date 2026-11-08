"""Private S3-compatible media, with no download route for original DICOM."""
from pathlib import PurePosixPath
from functools import cached_property
from urllib.parse import urlparse
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
import boto3
from botocore.exceptions import ClientError


def validate_key(name):
    if not name or '\\' in name or name.startswith('/') or any(p in {'', '.', '..'} for p in name.split('/')):
        raise SuspiciousFileOperation('Invalid object key')
    return str(PurePosixPath(name))


@deconstructible
class PrivateImageStorage(Storage):
    """URLs are short-lived bearer grants for approved display images only.

    Callers remain responsible for case-level permission checks before rendering
    a field URL. This storage must not be used to bypass a private-case policy.
    """
    @cached_property
    def client(self):
        required = ['R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_IMAGE_BUCKET']
        if any(not getattr(settings, k, '') for k in required):
            raise ImproperlyConfigured('Private object storage configuration is incomplete')
        endpoint = urlparse(settings.R2_ENDPOINT_URL)
        if endpoint.scheme != 'https' or not endpoint.hostname or not endpoint.hostname.endswith('.r2.cloudflarestorage.com') or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in {'', '/'}:
            raise ImproperlyConfigured('Use the HTTPS R2 S3 endpoint from the dashboard')
        return boto3.client('s3', endpoint_url=settings.R2_ENDPOINT_URL, region_name='auto',
                            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY)

    @property
    def bucket(self):
        return settings.R2_IMAGE_BUCKET

    def _image_key(self, name):
        name = validate_key(name)
        if PurePosixPath(name).suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
            raise SuspiciousFileOperation('Only display images are allowed in image storage')
        return name

    def _open(self, name, mode='rb'):
        if mode not in {'rb', 'r'}:
            raise ValueError('Object storage only opens files for reading')
        name = self._image_key(name)
        return File(self.client.get_object(Bucket=self.bucket, Key=name)['Body'], name=name)

    def _save(self, name, content):
        name = self._image_key(name)
        types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
        self.client.upload_fileobj(content, self.bucket, name,
            ExtraArgs={'ContentType': types[PurePosixPath(name).suffix.lower()], 'CacheControl': 'private, max-age=60'})
        return name

    def exists(self, name):
        name = self._image_key(name)
        try:
            self.client.head_object(Bucket=self.bucket, Key=name)
            return True
        except ClientError as error:
            if error.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
                return False
            raise

    def size(self, name):
        return self.client.head_object(Bucket=self.bucket, Key=self._image_key(name))['ContentLength']

    def delete(self, name):
        raise NotImplementedError('Object deletion requires an explicit retention workflow')

    def url(self, name):
        name = self._image_key(name)
        ttl = settings.R2_SIGNED_URL_SECONDS
        if not 30 <= ttl <= 900:
            raise ImproperlyConfigured('Signed image URL expiry must be 30-900 seconds')
        return self.client.generate_presigned_url('get_object', Params={'Bucket': self.bucket, 'Key': name}, ExpiresIn=ttl)


def quarantine_dicom(content, key):
    """Write an approved original to a separate private bucket. Never return a URL.

    This is an explicit execution primitive, not automatic consent or validation.
    The caller must authorize retention and complete DICOM content checks.
    """
    key = validate_key(key)
    if PurePosixPath(key).suffix.lower() != '.dcm':
        raise SuspiciousFileOperation('DICOM quarantine accepts .dcm keys only')
    if not getattr(settings, 'R2_DICOM_BUCKET', '') or settings.R2_DICOM_BUCKET == settings.R2_IMAGE_BUCKET:
        raise ImproperlyConfigured('DICOM quarantine must use a distinct private bucket')
    storage = PrivateImageStorage()
    storage.client.upload_fileobj(content, settings.R2_DICOM_BUCKET, key,
        ExtraArgs={'ContentType': 'application/dicom', 'CacheControl': 'no-store'})
    return key
