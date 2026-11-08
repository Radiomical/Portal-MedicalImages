"""Clinical shell and viewer use synthetic fixtures only."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from blog.models import Post
from users.models import FilePost

class ClinicalInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('clinical-fixture', password=None)
        self.post = Post.objects.create(title='Synthetic case', content='Fictional overview', author=self.user, clinical_case='Fictional clinical case', medical_report='Fictional example report')
        for n in range(2):
            FilePost.objects.create(post=self.post, header_image='synthetic/cover.jpg', axial_images=f'synthetic/slice-{n}.jpg')

    def test_home_has_local_assets_and_no_trackers(self):
        response = self.client.get('/')
        for text in ['css/clinical.css', 'js/clinical.js', 'Skip to content', 'viewport', 'Latest cases']:
            self.assertContains(response, text)
        for text in ['googletagmanager', 'WebFont', 'jquery', 'js/script.js']:
            self.assertNotContains(response, text)
        self.assertContains(response, '<body', count=1)

    def test_case_preserves_content_and_has_real_controls(self):
        response = self.client.get(reverse('blog:blog_page', args=[self.post.title, self.post.pk]))
        for text in ['Fictional overview', 'Fictional clinical case', 'Fictional example report', 'data-series', 'type="range"', 'slice 1 of 2', 'Not a diagnostic viewer']:
            self.assertContains(response, text)
        self.assertNotContains(response, 'MEDIR')

    def test_empty_results_and_query_are_escaped(self):
        response = self.client.get('/search/', {'q': '<script>&test'})
        self.assertContains(response, 'No cases found')
        self.assertContains(response, '&lt;script&gt;&amp;test')
        self.assertNotContains(response, '<script>&test')

    def test_logout_is_post_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/users/logout/').status_code, 405)
        self.assertEqual(self.client.post('/users/logout/').status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_list_signs_only_current_page_images(self):
        from unittest.mock import patch
        for n in range(8):
            Post.objects.create(title=f'Synthetic other {n}', content='Fictional', author=self.user)
        with patch('blog.views.retrieve_first_post_image', return_value={}) as retrieve:
            self.client.get('/all-blogs/')
        self.assertEqual(len(retrieve.call_args.args[0]), 5)
        with patch('blog.views.retrieve_first_post_image', return_value={}) as retrieve:
            self.client.get('/search/', {'q': 'Synthetic'})
        self.assertEqual(len(retrieve.call_args.args[0]), 5)
