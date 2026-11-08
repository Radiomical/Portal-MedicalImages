"""Synthetic storage-aware upload and failure tests. No patient images."""
import io
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from blog.models import Post
from users.models import FilePost, OriginalDicom


def jpeg(name='patient-looking-name.jpg'):
    out=io.BytesIO();Image.new('RGB',(8,8),'white').save(out,'JPEG')
    return SimpleUploadedFile(name,out.getvalue(),content_type='image/jpeg')


def dicom(name='patient-looking-name.dcm'):
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
    meta=FileMetaDataset();meta.TransferSyntaxUID=ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID=SecondaryCaptureImageStorage;meta.MediaStorageSOPInstanceUID=generate_uid()
    d=FileDataset(None,{},file_meta=meta,preamble=b'\0'*128)
    d.SOPClassUID=meta.MediaStorageSOPClassUID;d.SOPInstanceUID=meta.MediaStorageSOPInstanceUID
    d.Rows=d.Columns=8;d.SamplesPerPixel=1;d.PhotometricInterpretation='MONOCHROME2'
    d.BitsAllocated=d.BitsStored=8;d.HighBit=7;d.PixelRepresentation=0;d.PixelData=b'\x40'*64
    out=io.BytesIO();d.save_as(out,enforce_file_format=True)
    return SimpleUploadedFile(name,out.getvalue(),content_type='application/dicom')


class StorageUploadTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('synthetic-storage',password=None)
        self.client.force_login(self.user)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.override=override_settings(MEDIA_ROOT=self.temp.name+'/media',PRIVATE_DICOM_ROOT=self.temp.name+'/private')
        self.override.enable();self.addCleanup(self.override.disable)

    def data(self,kind='JPEG, JPG',retain='No',cover=None):
        return {'title':'Synthetic storage case','content':'Generated fixture only','category':'Abdomen','medical_findings':'Moderada','format':kind,'accepted_data_use':retain,'header_image':cover or jpeg()}

    def test_upload_never_uses_original_filename(self):
        response=self.client.post('/users/profile/new-post/',self.data())
        self.assertFalse(response.context['error'])
        key=FilePost.objects.get().header_image.name
        self.assertRegex(key,r'^images/[0-9a-f]{32}\.jpg$')
        self.assertNotIn('patient',key)

    def test_invalid_series_leaves_no_case_or_files(self):
        data=self.data();data['axial_image']=SimpleUploadedFile('bad.jpg',b'not jpeg')
        response=self.client.post('/users/profile/new-post/',data)
        self.assertTrue(response.context['error']);self.assertFalse(Post.objects.exists())
        self.assertFalse(list(Path(self.temp.name).rglob('*.jpg')))

    @override_settings(DICOM_RETENTION_ENABLED=True)
    def test_original_is_private_and_manifest_has_no_url(self):
        response=self.client.post('/users/profile/new-post/',self.data('DICOM','Si',dicom()))
        self.assertFalse(response.context['error'])
        original=OriginalDicom.objects.get()
        self.assertTrue((Path(self.temp.name)/'private'/original.object_key).is_file())
        self.assertFalse(list((Path(self.temp.name)/'media').rglob('*.dcm')))
        self.assertFalse(hasattr(original,'url'))
        self.assertEqual(len(original.sha256),64)
        with self.assertRaises(ProtectedError):Post.objects.get().delete()

    def test_retention_requires_explicit_enablement(self):
        response=self.client.post('/users/profile/new-post/',self.data('DICOM','Si',dicom()))
        self.assertTrue(response.context['error']);self.assertFalse(Post.objects.exists())
        self.assertFalse(list(Path(self.temp.name).rglob('*.*')))

    def test_storage_failure_on_edit_preserves_existing_case(self):
        p=Post.objects.create(title='Existing synthetic case',content='Keep this',author=self.user)
        old=FilePost.objects.create(post=p,header_image='synthetic/old.jpg')
        with patch('users.uploads.default_storage.save',side_effect=OSError('synthetic failure')):
            response=self.client.post(reverse('blog:edit_blog',args=[p.pk]),self.data())
        self.assertTrue(response.context['error']);p.refresh_from_db()
        self.assertEqual(p.title,'Existing synthetic case')
        self.assertEqual(FilePost.objects.get().pk,old.pk)

    @override_settings(MEDIA_STORAGE='r2',DICOM_RETENTION_ENABLED=True)
    def test_remote_conversion_uses_storage_and_separate_quarantine(self):
        with patch('users.uploads.default_storage.save',side_effect=lambda key,content:key) as save, patch('users.uploads.quarantine_dicom',side_effect=lambda content,key:key) as quarantine:
            response=self.client.post('/users/profile/new-post/',self.data('DICOM','Si',dicom()))
        self.assertFalse(response.context['error'])
        self.assertEqual(save.call_count,1);self.assertEqual(quarantine.call_count,1)
        self.assertEqual(OriginalDicom.objects.get().storage_location,'r2')
        self.assertFalse(list(Path(self.temp.name).rglob('*.jpg')))

    @override_settings(MAX_IMAGE_UPLOAD_BYTES=4)
    def test_size_bound_before_writes(self):
        response=self.client.post('/users/profile/new-post/',self.data())
        self.assertTrue(response.context['error']);self.assertFalse(Post.objects.exists())

    def test_successful_edit_saves_all_form_fields_and_replaces_references(self):
        p=Post.objects.create(title='Existing fixture',content='Old synthetic',author=self.user)
        old=FilePost.objects.create(post=p,header_image='synthetic/old.jpg')
        data=self.data();data['sequential']='Synthetic sequence';data['medical_findings']='Baja'
        response=self.client.post(reverse('blog:edit_blog',args=[p.pk]),data)
        self.assertEqual(response.status_code,302);p.refresh_from_db()
        self.assertEqual(p.sequential,'Synthetic sequence');self.assertEqual(p.medical_findings,'Baja')
        self.assertNotEqual(FilePost.objects.get().pk,old.pk)

    @override_settings(DICOM_RETENTION_ENABLED=True)
    def test_private_root_cannot_be_inside_media(self):
        with override_settings(PRIVATE_DICOM_ROOT=self.temp.name+'/media/private'):
            response=self.client.post('/users/profile/new-post/',self.data('DICOM','Si',dicom()))
        self.assertTrue(response.context['error']);self.assertFalse(Post.objects.exists())
