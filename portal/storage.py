"""S3-compatible images with opt-in public URLs; original DICOM stays private."""
from pathlib import PurePosixPath
from functools import cached_property
from urllib.parse import urlparse, quote
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from .media_config import validate_public_image_origin
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config


def validate_key(name):
    if not name or '\\' in name or name.startswith('/') or any(p in {'', '.', '..'} for p in name.split('/')):
        raise SuspiciousFileOperation('Invalid object key')
    return str(PurePosixPath(name))


@deconstructible
class PrivateImageStorage(Storage):
    """Display-image storage; signed by default, explicitly public when configured.

    Public mode is only for a bucket whose entire contents may be published.
    It is not an access-control mechanism for private cases. The class name is
    retained for migration/deployment compatibility.
    """
    @cached_property
    def client(self):
        required = ['R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_IMAGE_BUCKET']
        if any(not getattr(settings, k, '') for k in required):
            raise ImproperlyConfigured('Private object storage configuration is incomplete')
        endpoint = urlparse(settings.R2_ENDPOINT_URL)
        if endpoint.scheme != 'https' or not endpoint.hostname or not endpoint.hostname.endswith('.r2.cloudflarestorage.com') or endpoint.username or endpoint.password or endpoint.netloc != endpoint.hostname or endpoint.query or endpoint.fragment or endpoint.path not in {'', '/'}:
            raise ImproperlyConfigured('Use the HTTPS R2 S3 endpoint from the dashboard')
        return boto3.client('s3', endpoint_url=settings.R2_ENDPOINT_URL, region_name='auto', config=Config(signature_version='s3v4'),
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
        cache_control = ('public, max-age=31536000, immutable' if self.public_base_url
                         else 'private, max-age=60')
        create_object(self.client, self.bucket, name, content,
                      types[PurePosixPath(name).suffix.lower()], cache_control)
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

    @property
    def public_base_url(self):
        origin = validate_public_image_origin(getattr(settings, 'R2_IMAGE_PUBLIC_BASE_URL', ''))
        if origin and (not settings.R2_IMAGE_BUCKET or not settings.R2_DICOM_BUCKET
                       or settings.R2_IMAGE_BUCKET == settings.R2_DICOM_BUCKET):
            raise ImproperlyConfigured('Public images require distinct image and private DICOM buckets')
        return origin

    def url(self, name):
        name = self._image_key(name)
        origin = self.public_base_url
        if origin:
            # Never contact R2, HEAD an object, or add per-request query tokens.
            return origin + '/' + quote(name, safe='/')
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
    create_object(storage.client, settings.R2_DICOM_BUCKET, key, content,
                  'application/dicom', 'no-store')
    return key


def create_object(client, bucket, key, content, content_type, cache_control):
    """Atomic create-only write: never replace an existing retained object.

    A failed or uncertain write must be reconciled by the caller, not retried
    without a condition. R2 evaluates IfNoneMatch atomically at commit.
    """
    try:
        client.put_object(Bucket=bucket, Key=key, Body=content,
                          ContentType=content_type, CacheControl=cache_control,
                          IfNoneMatch='*')
    except ClientError as error:
        if error.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 412:
            raise FileExistsError('Object key already exists; original preserved') from error
        raise
