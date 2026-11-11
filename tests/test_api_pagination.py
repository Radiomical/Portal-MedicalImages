from django.contrib.auth.models import User
from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from blog.models import Post


class CasePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('pagination-synthetic', 'pagination@example.invalid')
        cls.token = Token.objects.create(user=cls.user)
        Post.objects.bulk_create([Post(title=f'Synthetic {i}', content='Generated', author=cls.user) for i in range(113)])

    def fetch(self, **params):
        return self.client.get('/api/get/posts/', params, HTTP_AUTHORIZATION='Token ' + self.token.key)

    def test_default_is_bounded_and_preserves_array_and_author_email(self):
        response = self.fetch()
        self.assertEqual(len(response.json()), 50)
        self.assertEqual(response.json()[0]['autor']['email'], self.user.email)
        self.assertIn('rel="next"', response['Link'])
        self.assertIn('page_size=50', response['Link'])
        self.assertEqual(set(response.json()[0]), {'titulo', 'autor', 'categoria', 'url'})

    def test_keyset_pages_cover_all_cases_once(self):
        after, titles = 0, []
        while True:
            response = self.fetch(after=after, page_size=17)
            titles.extend(row['titulo'] for row in response.json())
            if 'Link' not in response:
                break
            from urllib.parse import urlparse, parse_qs
            after = int(parse_qs(urlparse(response['Link'].split('>')[0][1:]).query)['after'][0])
        self.assertEqual(len(titles), 113)
        self.assertEqual(len(set(titles)), 113)

    def test_query_count_is_constant(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(len(self.fetch(page_size=100).json()), 100)
        self.assertLessEqual(len(queries), 2)

    def test_bad_limits_rejected(self):
        for params in [{'after': -1}, {'after': 'x'}, {'after': 10**30}, {'page_size': 0}, {'page_size': 101}, {'page_size': 'x'}]:
            self.assertEqual(self.fetch(**params).status_code, 400)

    def test_empty_final_page(self):
        response = self.fetch(after=9223372036854775807)
        self.assertEqual(response.json(), [])
        self.assertNotIn('Link', response)

    def test_search_keeps_substring_semantics(self):
        Post.objects.create(title='Generated FoObAr title', content='Generated', author=self.user)
        response = self.client.get('/search/', {'q': 'oObA'})
        self.assertContains(response, 'Generated FoObAr title')

    def test_postgres_search_indexes_are_valid(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL-only expression indexes')
        with connection.cursor() as cursor:
            cursor.execute("SELECT c.relname, i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname IN ('post_title_upper_trgm','post_content_upper_trgm')")
            self.assertEqual(dict(cursor.fetchall()), {'post_title_upper_trgm': True, 'post_content_upper_trgm': True})
