import hashlib
import io
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from blog.models import Post
from users.models import Case, Series, Image
from users.media_reconciliation import audit_objects, measure


class ReconciliationTests(TestCase):
    def setUp(self):
        post = Post.objects.create(title='Generated audit case', content='Synthetic', author=User.objects.create_user('audit-synthetic'))
        case = Case.objects.create(post=post, source_sha256='a'*64)
        self.series = Series.objects.create(case=case, plane='axial', expected_image_count=1)
        self.raw = b'generated-audit-fixture'
        self.image = Image.objects.create(series=self.series, position=0, object_key='images/generated.jpg', byte_size=len(self.raw), sha256=hashlib.sha256(self.raw).hexdigest(), storage_location='filesystem')

    def test_match_is_read_only_and_closes_stream(self):
        stream = io.BytesIO(self.raw)
        with patch('users.media_reconciliation.default_storage.open', return_value=stream), patch('users.media_reconciliation.default_storage.url', side_effect=AssertionError('No signatures')):
            result = audit_objects(1024,1024)
        self.assertEqual(result['matched'],1)
        self.assertTrue(stream.closed)
        self.image.refresh_from_db()
        self.assertEqual(self.image.verification_state,'unverified')

    def test_mismatch_and_unknown_never_adopt_measured_hash(self):
        with patch('users.media_reconciliation.default_storage.open', return_value=io.BytesIO(b'changed')):
            self.assertEqual(audit_objects(1024,1024)['mismatch'],1)
        Image.objects.filter(pk=self.image.pk).update(sha256='',byte_size=None)
        with patch('users.media_reconciliation.default_storage.open', return_value=io.BytesIO(self.raw)):
            self.assertEqual(audit_objects(1024,1024)['unknown_baseline'],1)
        self.assertEqual(Image.objects.get().sha256,'')

    def test_missing_and_unknown_provider_error_are_distinct(self):
        for error, label in [(FileNotFoundError(),'missing'),(OSError('private-provider-body'),'read_error')]:
            with patch('users.media_reconciliation.default_storage.open',side_effect=error):
                self.assertEqual(audit_objects(1024,1024)[label],1)

    def test_guard_and_default_summary_never_read_objects(self):
        with patch('users.media_reconciliation.default_storage.open',side_effect=AssertionError('No reads')):
            call_command('media_reconcile',stdout=io.StringIO())
            with self.assertRaises(CommandError):
                call_command('media_reconcile','--read-objects',stdout=io.StringIO())

    def test_budget_stops_bounded_read(self):
        with patch('users.media_reconciliation.default_storage.open',return_value=io.BytesIO(self.raw)):
            self.assertEqual(audit_objects(4,4)['budget_or_validation_error'],1)

    def test_shared_key_only_read_once(self):
        Image.objects.create(series=self.series,position=1,object_key=self.image.object_key,byte_size=self.image.byte_size,sha256=self.image.sha256,storage_location='filesystem')
        with patch('users.media_reconciliation.default_storage.open',return_value=io.BytesIO(self.raw)) as opened:
            result=audit_objects(1024,1024)
        self.assertEqual(opened.call_count,1)
        self.assertEqual(result['duplicate_references'],1)

    def test_shared_key_conflicting_baselines_are_not_hidden(self):
        Image.objects.create(series=self.series,position=1,object_key=self.image.object_key,byte_size=7,sha256='b'*64,storage_location='filesystem')
        with patch('users.media_reconciliation.default_storage.open',return_value=io.BytesIO(self.raw)):
            self.assertEqual(audit_objects(1024,1024)['conflicting_baselines'],1)

    def test_legacy_and_current_label_share_effective_backend_identity(self):
        Image.objects.create(series=self.series,position=1,object_key=self.image.object_key,byte_size=7,sha256='b'*64,storage_location='legacy')
        with patch('users.media_reconciliation.default_storage.open',return_value=io.BytesIO(self.raw)) as opened:
            result=audit_objects(1024,1024)
        self.assertEqual(opened.call_count,1)
        self.assertEqual(result['duplicate_references'],1)
        self.assertEqual(result['conflicting_baselines'],1)
        self.assertEqual(result['bytes_read'],len(self.raw))
