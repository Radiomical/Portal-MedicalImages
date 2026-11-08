"""Faithful Spanish UI and legacy account/editor behavior on synthetic data."""
from html.parser import HTMLParser
from django.contrib.auth.models import User
from django.test import TestCase
from blog.models import Post
from users.models import UserProfile

class InputParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []
    def handle_starttag(self, tag, attrs):
        if tag == 'input':
            self.inputs.append(dict(attrs))

class SpanishInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('spanish-fixture', email='ui@example.invalid', password=None)
        UserProfile.objects.create(user=self.user, country='Spain', work_location='Synthetic institute')
        self.client.force_login(self.user)

    def test_home_preserves_original_copy_and_sections(self):
        response = self.client.get('/')
        for text in ('lang="es"', 'Entradas del servidor', 'PORTAL.RADIOLOGYMODELS', 'Sube tus entradas para compartirlas con la comunidad.', 'Ver últimas entradas', 'Últimas entradas', 'Ver todas las entradas'):
            self.assertContains(response, text)

    def test_create_retains_every_legacy_field_and_consent(self):
        response = self.client.get('/users/profile/new-post/')
        for name in ('title','content','category','fisiopathology','clinical_case','clinical_signs','doppler','medical_findings','preparation','sequential','pediatrics','medical_report','seram_link','radiopedia_link','format','accepted_data_use','cie_11_tagging','interested_region','other_interested_region','header_image','axial_image','coronal_image','sagital_image','axial_description','coronal_description','sagital_description'):
            self.assertContains(response, 'name="' + name + '"')
        self.assertContains(response, 'Al aceptar participar tu estudio se cargará en una base de datos')

    def test_editor_roundtrips_quoted_title_and_existing_links(self):
        title = 'Generated " autofocus onfocus="not-code'
        post = Post.objects.create(title=title, content='Synthetic only', author=self.user, seram_link='https://example.invalid/seram', radiopedia_link='https://example.invalid/reference')
        response = self.client.get(f'/edit-blog/{post.pk}/')
        self.assertEqual(response.status_code, 200)
        parser = InputParser()
        parser.feed(response.content.decode())
        title_input = next(item for item in parser.inputs if item.get('name') == 'title')
        self.assertEqual(title_input['value'], title)
        self.assertNotIn('autofocus', title_input)
        self.assertNotIn('onfocus', title_input)
        for name, value in [('seram_link',post.seram_link),('radiopedia_link',post.radiopedia_link)]:
            self.assertEqual(next(item for item in parser.inputs if item.get('name') == name)['value'], value)

    def test_profile_get_prefills_without_writing(self):
        response = self.client.get('/users/profile/')
        self.assertEqual(response.context['form2'].initial['user_work_location'], 'Synthetic institute')
        self.assertEqual(response.context['form2'].initial['user_country'], 'Spain')
        self.assertContains(response, 'id="password_update_form"')
        self.assertContains(response, 'id="profile_update_form"')
        self.assertEqual(UserProfile.objects.get(user=self.user).work_location, 'Synthetic institute')
