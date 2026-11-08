"""Storage-aware educational uploads. This is not an anonymization pipeline."""
import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

import pydicom
from PIL import Image
from django.conf import settings
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage, FileSystemStorage
from portal.storage import quarantine_dicom
from .models import FilePost, OriginalDicom


@dataclass
class PreparedImage:
    field: str
    jpeg: bytes
    original: bytes | None


def prepare_images(cleaned, uploads):
    """Decode the entire submission before writing any database row or object."""
    result = []
    total = 0
    is_dicom = cleaned['format'] == 'DICOM'
    for field, files in uploads.items():
        for upload in files:
            upload.seek(0)
            raw = upload.read(settings.MAX_IMAGE_UPLOAD_BYTES + 1)
            total += len(raw)
            if len(raw) > settings.MAX_IMAGE_UPLOAD_BYTES or total > settings.MAX_CASE_UPLOAD_BYTES:
                raise ValidationError('Upload exceeds the configured file or case size limit.')
            try:
                if is_dicom:
                    dataset = pydicom.dcmread(io.BytesIO(raw))
                    if int(getattr(dataset, 'NumberOfFrames', 1)) != 1:
                        raise ValidationError('Multi-frame DICOM is not supported by this educational converter.')
                    if int(dataset.Rows) * int(dataset.Columns) > settings.MAX_IMAGE_PIXELS:
                        raise ValidationError('Image exceeds the configured pixel limit.')
                    array = dataset.pixel_array
                    if array.ndim != 2:
                        raise ValidationError('Only single-frame grayscale DICOM is supported.')
                    # Preserve the inherited educational conversion, not diagnostic windowing.
                    image = Image.fromarray(array.astype(float)).convert('L')
                else:
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.format != 'JPEG':
                            raise ValidationError('Display uploads must contain valid JPEG data.')
                        if source.width * source.height > settings.MAX_IMAGE_PIXELS:
                            raise ValidationError('Image exceeds the configured pixel limit.')
                        source.load()
                        image = source.convert('RGB')
                output = io.BytesIO()
                image.save(output, format='JPEG')
                result.append(PreparedImage(field, output.getvalue(), raw if is_dicom else None))
            except ValidationError:
                raise
            except Exception as error:
                raise ValidationError('An image could not be decoded. No case changes were saved.') from error
    if not any(item.field == 'header_image' for item in result):
        raise ValidationError('A cover image is required.')
    if is_dicom and cleaned.get('accepted_data_use') == 'Si':
        if not settings.DICOM_RETENTION_ENABLED:
            raise ValidationError('Original DICOM retention is not enabled. Contact the administrator before submitting retained originals.')
        if settings.MEDIA_STORAGE == 'filesystem':
            root = Path(settings.PRIVATE_DICOM_ROOT).resolve()
            media = Path(settings.MEDIA_ROOT).resolve()
            if root == media or root.is_relative_to(media):
                raise ImproperlyConfigured('Private DICOM storage must be outside public media.')
    return result


def store_case_images(post, cleaned, prepared):
    """Call inside a DB transaction. Storage objects are never overwritten.

    Object storage has no cross-system transaction. If a later write fails,
    newly created objects may be unreferenced; retain them for reconciliation,
    never guess at deleting an object after an uncertain response.
    """
    cover = next(item for item in prepared if item.field == 'header_image')
    header_key = default_storage.save('images/' + uuid.uuid4().hex + '.jpg', ContentFile(cover.jpeg))
    retain = cleaned['format'] == 'DICOM' and cleaned.get('accepted_data_use') == 'Si'
    common = {key: cleaned.get(key) for key in ['format', 'accepted_data_use', 'cie_11_tagging', 'interested_region', 'other_interested_region']}
    if common['accepted_data_use'] != 'Si':
        common.update(cie_11_tagging=None, interested_region=None, other_interested_region=None)
    series = [item for item in prepared if item.field != 'header_image']
    if not series:
        FilePost.objects.create(post=post, header_image=header_key, **common)
    for item in series:
        key = default_storage.save('images/' + uuid.uuid4().hex + '.jpg', ContentFile(item.jpeg))
        description = item.field.replace('_images', '_description')
        FilePost.objects.create(post=post, header_image=header_key, **{item.field: key, description: cleaned.get(description, '')}, **common)
    if retain:
        for item in prepared:
            key = 'originals/' + uuid.uuid4().hex + '.dcm'
            if settings.MEDIA_STORAGE == 'r2':
                quarantine_dicom(ContentFile(item.original), key)
                location = 'r2'
            else:
                private = FileSystemStorage(location=settings.PRIVATE_DICOM_ROOT, file_permissions_mode=0o600, directory_permissions_mode=0o700)
                key = private.save(key, ContentFile(item.original))
                location = 'filesystem'
            OriginalDicom.objects.create(post=post, object_key=key, storage_location=location,
                sha256=hashlib.sha256(item.original).hexdigest(), byte_size=len(item.original))
