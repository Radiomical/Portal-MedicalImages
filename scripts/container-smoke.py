"""Run inside the final image, without production credentials or data."""
import importlib
import io
import os
import pathlib
import ssl
import sys
import tempfile

assert sys.version_info[:2] == (3, 13)
assert os.getuid() == 65532
assert sys.prefix == '/opt/venv', sys.prefix
assert not pathlib.Path('/bin/sh').exists()
assert not pathlib.Path('/usr/bin/pip').exists()
assert pathlib.Path(ssl.get_default_verify_paths().cafile).is_file()
for name in ('django', 'gunicorn', 'boto3', 'numpy', 'pydicom', 'psycopg'):
    importlib.import_module(name)
from PIL import Image
buffer = io.BytesIO()
Image.new('RGB', (8, 8)).save(buffer, format='JPEG')
buffer.seek(0)
Image.open(buffer).load()
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
meta = Dataset()
meta.TransferSyntaxUID = ExplicitVRLittleEndian
meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
meta.MediaStorageSOPInstanceUID = generate_uid()
ds = FileDataset(None, {}, file_meta=meta, preamble=b'\0' * 128)
ds.Rows = ds.Columns = 2
ds.SamplesPerPixel = 1
ds.PhotometricInterpretation = 'MONOCHROME2'
ds.BitsAllocated = ds.BitsStored = 16
ds.HighBit = 15
ds.PixelRepresentation = 0
ds.PixelData = b'\0\0' * 4
assert ds.pixel_array.shape == (2, 2)
with tempfile.TemporaryDirectory() as tmp:
    from pydicom import dcmread
    path = pathlib.Path(tmp) / 'synthetic.dcm'
    ds.save_as(path, enforce_file_format=True)
    assert dcmread(path).pixel_array.shape == (2, 2)
print('Nonroot, CA trust, virtualenv, PostgreSQL/JPEG/DICOM imports and synthetic decode passed.')
