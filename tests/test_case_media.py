from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from blog.models import Post
from users.models import Case, Series, Image, FilePost
from users.case_media import backfill_case, projection, verify_case


class CaseMediaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('normalized-synthetic')
        self.post = Post.objects.create(title='Generated case', content='Synthetic only', author=self.user)
        self.a = FilePost.objects.create(post=self.post, header_image='images/opaque-cover.jpg', axial_images='images/slice-a.jpg', axial_description='None', accepted_data_use='Si')
        self.b = FilePost.objects.create(post=self.post, header_image='images/opaque-cover.jpg', axial_images='images/slice-b.jpg', coronal_images='images/coronal.jpg', axial_description='Generated description', accepted_data_use='No')

    def test_backfill_is_idempotent_and_does_not_touch_objects(self):
        with patch('django.core.files.storage.default_storage.open', side_effect=AssertionError('No object reads')), patch('django.core.files.storage.default_storage.url', side_effect=AssertionError('No signatures')):
            self.assertTrue(backfill_case(self.post.pk))
            self.assertFalse(backfill_case(self.post.pk))
        case = Case.objects.get(pk=self.post.pk)
        self.assertTrue(verify_case(case, projection(self.post)))
        self.assertEqual(case.pk, self.post.pk)
        self.assertEqual(case.review_state, 'legacy_unverified')
        self.assertEqual(Image.objects.count(), 4)  # One shared cover, two axial, one coronal.
        self.assertEqual(Image.objects.filter(series__plane='axial').values_list('position', flat=True).get(position=1), 1)
        self.assertEqual(Series.objects.get(plane='axial').description, 'Generated description')
        self.assertEqual(case.legacy_metadata['accepted_data_use'], ['Si', 'No'])
        for image in Image.objects.all():
            self.assertIsNone(image.byte_size)
            self.assertEqual(image.sha256, '')
            self.assertEqual(image.storage_location, 'legacy')
            self.assertEqual(image.verification_state, 'unverified')
            self.assertIsNone(image.original_id)
        self.assertEqual(FilePost.objects.count(), 2)
        self.assertEqual(self.client.get(reverse('blog:blog_page', args=[self.post.title, self.post.pk])).status_code, 200)

    def test_changed_source_is_not_silently_overwritten(self):
        backfill_case(self.post.pk)
        FilePost.objects.filter(pk=self.a.pk).update(axial_images='images/replaced.jpg')
        with self.assertRaises(ValueError):
            backfill_case(self.post.pk)
        self.assertTrue(Image.objects.filter(object_key='images/slice-a.jpg').exists())

    def test_equivalence_checks_references_not_just_counts(self):
        backfill_case(self.post.pk)
        Image.objects.filter(object_key='images/slice-a.jpg').update(object_key='images/wrong.jpg')
        with self.assertRaises(ValueError):
            verify_case(Case.objects.get(pk=self.post.pk), projection(self.post))

    def test_dry_run_is_read_only_and_apply_has_database_guard(self):
        output = StringIO()
        call_command('case_media_backfill', stdout=output)
        self.assertEqual(Case.objects.count(), 0)
        self.assertNotIn('images/', output.getvalue())
        for args in [[], ['--quiescent-source', '--expected-database', 'wrong-database']]:
            with self.assertRaises(CommandError):
                call_command('case_media_backfill', '--apply', *args, stdout=StringIO())
        backfill_case(self.post.pk)
        call_command('case_media_backfill', '--verify', stdout=StringIO())

    def test_empty_case_projects_without_fabricating_images(self):
        post = Post.objects.create(title='Empty generated case', content='Synthetic', author=self.user)
        backfill_case(post.pk)
        case = Case.objects.get(pk=post.pk)
        self.assertEqual(case.cover_key, '')
        self.assertEqual(case.series.count(), 0)

    def test_positions_unique_and_verified_requires_metadata(self):
        backfill_case(self.post.pk)
        image = Image.objects.filter(series__plane='axial').first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Image.objects.create(series=image.series, position=image.position, object_key='images/duplicate.jpg')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Image.objects.filter(pk=image.pk).update(verification_state='verified')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Series.objects.filter(pk=image.series_id).update(plane='unknown')
