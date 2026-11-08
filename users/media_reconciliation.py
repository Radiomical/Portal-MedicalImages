"""Explicit read-back audit only. Never signs, uploads, deletes or fixes objects."""
import hashlib
from collections import Counter
from django.core.files.storage import default_storage, FileSystemStorage
from django.conf import settings
from portal.storage import PrivateImageStorage, validate_key
from .models import Image, OriginalDicom


def measure(stream, limit):
    size, digest = 0, hashlib.sha256()
    while True:
        block = stream.read(min(1024 * 1024, limit - size + 1))
        if not block:
            return size, digest.hexdigest()
        size += len(block)
        if size > limit:
            raise ValueError('Audit byte budget exceeded.')
        digest.update(block)


def open_original(item):
    key = validate_key(item.object_key)
    if item.storage_location == 'filesystem':
        return FileSystemStorage(location=settings.PRIVATE_DICOM_ROOT).open(key, 'rb')
    if item.storage_location == 'r2':
        storage = PrivateImageStorage()
        if not settings.R2_DICOM_BUCKET or settings.R2_DICOM_BUCKET == storage.bucket:
            raise ValueError('Distinct original bucket required.')
        return storage.client.get_object(Bucket=settings.R2_DICOM_BUCKET, Key=key)['Body']
    raise ValueError('Unknown original storage.')


def audit_objects(byte_budget, max_object_bytes, include_originals=False):
    """Aggregate outcome, no private keys in output. Read current storage only.

    A matching digest is object integrity, not anonymity or publication approval.
    Unknown legacy hashes are measured but never adopted as a trusted baseline.
    The command caller must arrange a quiescent source and authorized scope.
    """
    result = Counter()
    seen = {}
    sources = [('display', Image.objects.order_by('pk').iterator(chunk_size=100))]
    if include_originals:
        sources.append(('original', OriginalDicom.objects.order_by('pk').iterator(chunk_size=100)))
    for kind, items in sources:
        for item in items:
            location = item.storage_location
            effective_location = settings.MEDIA_STORAGE if kind == 'display' and location == 'legacy' else location
            identity = (kind, effective_location, item.object_key)
            baseline = (item.byte_size, item.sha256)
            if identity in seen:
                result['duplicate_references'] += 1
                if seen[identity] != baseline:
                    result['conflicting_baselines'] += 1
                continue
            seen[identity] = baseline
            result['references'] += 1
            if kind == 'display' and location not in ('legacy', settings.MEDIA_STORAGE):
                result['unavailable_storage'] += 1
                continue
            remaining = byte_budget - result['bytes_read']
            if remaining <= 0:
                result['budget_exhausted'] += 1
                return dict(result)
            limit = min(remaining, max_object_bytes)
            try:
                stream = open_original(item) if kind == 'original' else default_storage.open(validate_key(item.object_key), 'rb')
                try:
                    size, digest = measure(stream, limit)
                finally:
                    stream.close()
            except FileNotFoundError:
                result['missing'] += 1
                continue
            except ValueError:
                result['budget_or_validation_error'] += 1
                return dict(result)
            except Exception:
                # Provider failure is not proof of absence. Do not print provider
                # bodies that may contain object names, endpoints or credentials.
                result['read_error'] += 1
                return dict(result)
            result['bytes_read'] += size
            if not item.sha256 or item.byte_size is None:
                result['unknown_baseline'] += 1
            elif size != item.byte_size or digest != item.sha256:
                result['mismatch'] += 1
            else:
                result['matched'] += 1
    return dict(result)
