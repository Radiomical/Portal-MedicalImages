from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from blog.models import Post
from blog.views import case_cards
from users.case_media import backfill_case
from users.models import Case, FilePost, Image


class NormalizedReaderTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('reader-synthetic')
        self.post = Post.objects.create(title='Generated reader case', content='Synthetic', author=user)
        FilePost.objects.bulk_create([FilePost(post=self.post, header_image='images/cover.jpg', axial_images=f'images/slice-{n}.jpg', axial_description='Generated series') for n in range(120)])
        backfill_case(self.post.pk)

    def endpoint(self, index):
        return self.client.get(reverse('blog:series_slice', args=[self.post.pk, 'axial']), {'index': index})

    @override_settings(CASE_MEDIA_DUAL_WRITE=True, CASE_MEDIA_NORMALIZED_READ=True)
    def test_normalized_slice_matches_legacy_and_has_no_offset(self):
        with patch('blog.views.default_storage.url', side_effect=lambda key: '/fixture/' + key):
            with override_settings(CASE_MEDIA_NORMALIZED_READ=False):
                legacy = self.endpoint(75).json()
            with CaptureQueriesContext(connection) as queries:
                normalized = self.endpoint(75).json()
        self.assertEqual(normalized, legacy)
        self.assertFalse(any('OFFSET' in query['sql'] for query in queries))
        self.assertTrue(any('users_image' in query['sql'] for query in queries))
        self.assertEqual(self.endpoint(120).status_code, 404)

    @override_settings(CASE_MEDIA_DUAL_WRITE=True, CASE_MEDIA_NORMALIZED_READ=True)
    def test_detail_counts_and_description_match(self):
        url = reverse('blog:blog_page', args=[self.post.title, self.post.pk])
        with override_settings(CASE_MEDIA_NORMALIZED_READ=False):
            legacy = self.client.get(url)
        normalized = self.client.get(url)
        self.assertEqual(normalized.status_code, 200)
        self.assertEqual(normalized.context['axial_post_images_list'], legacy.context['axial_post_images_list'])
        self.assertEqual(normalized.context['axial_description'], legacy.context['axial_description'])
        self.assertContains(normalized, 'data-count="120"')
        self.assertContains(normalized, 'data-current-slice', count=1)

    @override_settings(CASE_MEDIA_DUAL_WRITE=True, CASE_MEDIA_NORMALIZED_READ=True)
    def test_stale_or_unmigrated_case_uses_legacy(self):
        Case.objects.filter(pk=self.post.pk).update(projection_stale=True)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.endpoint(0).status_code, 200)
        self.assertFalse(any('FROM "users_image"' in query['sql'] for query in queries))
        Case.objects.filter(pk=self.post.pk).delete()
        self.assertEqual(self.endpoint(0).status_code, 200)

    @override_settings(CASE_MEDIA_DUAL_WRITE=True, CASE_MEDIA_NORMALIZED_READ=True)
    def test_cards_use_verified_projection_or_legacy_fallback(self):
        self.assertEqual(case_cards().get(pk=self.post.pk).cover_key, 'images/cover.jpg')
        Case.objects.filter(pk=self.post.pk).update(projection_stale=True, cover_key='images/wrong.jpg')
        self.assertEqual(case_cards().get(pk=self.post.pk).cover_key, 'images/cover.jpg')

    @override_settings(CASE_MEDIA_DUAL_WRITE=True, CASE_MEDIA_NORMALIZED_READ=True)
    def test_corrupt_position_gap_does_not_shift_image(self):
        Image.objects.filter(series__plane='axial', position=0).delete()
        self.assertEqual(self.endpoint(0).status_code, 503)

    def test_blank_first_cover_preserved_even_if_later_cover_nonblank(self):
        first = FilePost.objects.filter(post=self.post).order_by('pk').first()
        first.header_image = ''
        first.save()
        Case.objects.filter(pk=self.post.pk).delete()
        backfill_case(self.post.pk)
        self.assertEqual(Case.objects.get(pk=self.post.pk).cover_key, '')
        self.assertEqual(Case.objects.get(pk=self.post.pk).legacy_metadata['cover_keys'], ['images/cover.jpg'])

    @override_settings(CASE_MEDIA_DUAL_WRITE=True, CASE_MEDIA_NORMALIZED_READ=True)
    def test_middle_and_trailing_gaps_are_unavailable_for_every_index(self):
        for position in (60, 119):
            with self.subTest(position=position):
                image = Image.objects.get(series__case_id=self.post.pk, series__plane='axial', position=position)
                data = {field: getattr(image, field) for field in ('series_id', 'position', 'object_key', 'legacy_file_id', 'legacy_description')}
                image.delete()
                for index in (0, 65, 119):
                    self.assertEqual(self.endpoint(index).status_code, 503)
                Image.objects.create(**data)
