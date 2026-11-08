from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from blog.models import Post
from users.models import FilePost


class BoundedViewerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user('bounded-synthetic', password=None)
        cls.post = Post.objects.create(title='Generated bounded case', content='Synthetic', author=user)
        FilePost.objects.bulk_create([FilePost(post=cls.post, header_image='synthetic/cover.jpg', axial_images=f'synthetic/slice-{n}.jpg') for n in range(120)])

    def endpoint(self, **params):
        return self.client.get(reverse('blog:series_slice', args=[self.post.pk, 'axial']), params)

    def test_detail_does_not_sign_or_embed_entire_series(self):
        with patch('blog.views.default_storage.url', return_value='/synthetic/cover.jpg') as url:
            response = self.client.get(reverse('blog:blog_page', args=[self.post.title, self.post.pk]))
        self.assertContains(response, 'data-count="120"')
        self.assertContains(response, 'data-current-slice', count=1)
        self.assertNotContains(response, 'slice-119.jpg')
        self.assertEqual(url.call_count, 0)

    def test_slice_signs_current_and_one_prefetch_only(self):
        with patch('blog.views.default_storage.url', side_effect=lambda key: '/test/' + key) as url:
            response = self.endpoint(index=50)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total'], 120)
        self.assertEqual([x['index'] for x in data['images']], [50, 51])
        self.assertEqual(url.call_count, 2)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(data['images'][0]['url'], '/test/synthetic/slice-50.jpg')

    def test_last_slice_has_no_extra_prefetch(self):
        self.assertEqual(len(self.endpoint(index=119).json()['images']), 1)

    def test_indices_and_plane_reject_invalid_input(self):
        for index, status in [('-1', 404), ('120', 404), ('invalid', 400)]:
            self.assertEqual(self.endpoint(index=index).status_code, status)
        self.assertEqual(self.client.get(reverse('blog:series_slice', args=[self.post.pk, 'dicom'])).status_code, 404)

    def test_cover_and_author_queries_do_not_scale_per_card(self):
        Post.objects.bulk_create([Post(title='Generated other', content='Synthetic', author_id=self.post.author_id) for _ in range(8)])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/all-blogs/')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 3)

    def test_series_order_is_stable_legacy_pk_not_anatomic_claim(self):
        first = self.endpoint(index=0).json()
        self.assertIn('slice-0.jpg', first['images'][0]['url'])
        self.assertEqual(self.endpoint(index=0).json()['images'][0]['url'], first['images'][0]['url'])
