from django.contrib.auth.models import User
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from blog.models import Post
from users.models import FilePost, OriginalDicom
from users.forms import SignupForm
from users.email_policy import email_user


class DomainPolicyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('policy-synthetic', ' Mixed@Example.invalid ', 'Synthetic-Password-39!')
        self.post = Post.objects.create(title='Generated policy case', content='Synthetic only', author=self.user)

    def test_new_confidence_is_unevaluated_not_automatically_high(self):
        self.assertEqual(self.post.medical_findings, 'Sin evaluar')

    def test_signup_normalizes_and_rejects_existing_normalized_email(self):
        data = {'username': 'new-synthetic', 'email': 'MIXED@example.invalid', 'password1': 'Synthetic-Password-39!', 'password2': 'Synthetic-Password-39!'}
        form = SignupForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        data['email'] = 'NEW@example.invalid'
        form = SignupForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['email'], 'new@example.invalid')

    def test_database_rejects_normalized_collision_but_allows_blank_nonlogin(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('duplicate-synthetic', 'mixed@example.invalid')
        User.objects.create_user('blank-one', '')
        User.objects.create_user('blank-two', '')
        self.assertIsNone(email_user(''))
        self.assertEqual(email_user(' mixed@example.invalid ').pk, self.user.pk)

    def test_login_is_case_and_outer_space_insensitive(self):
        response = self.client.post('/users/login/', {'email': 'mixed@EXAMPLE.invalid', 'password': 'Synthetic-Password-39!'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_invalid_domain_values_fail_at_database_boundary(self):
        for values in [{'category': 'invalid'}, {'medical_findings': 'invalid'}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Post.objects.filter(pk=self.post.pk).update(**values)
        for values in [{'format': 'invalid'}, {'accepted_data_use': 'OK'}, {'category': 'invalid'}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                FilePost.objects.create(post=self.post, header_image='synthetic/cover.jpg', **values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OriginalDicom.objects.create(post=self.post, object_key='originals/generated.dcm', storage_location='r2', sha256='x', byte_size=1)

    def test_retained_original_still_blocks_case_deletion(self):
        from django.db.models.deletion import ProtectedError
        OriginalDicom.objects.create(post=self.post, object_key='originals/generated.dcm', storage_location='r2', sha256='a'*64, byte_size=1)
        with self.assertRaises(ProtectedError):
            self.post.delete()

    def test_preflight_reports_only_aggregate_counts(self):
        from django.core.management import call_command
        from io import StringIO
        import json
        output = StringIO()
        call_command('domain_preflight', stdout=output)
        result = json.loads(output.getvalue())
        self.assertTrue(all(value == 0 for value in result.values()))
        self.assertNotIn('@', output.getvalue())

    def test_existing_high_confidence_is_preserved(self):
        high = 'Alta (confirmación anatomopatológica/quirúrgica)'
        Post.objects.filter(pk=self.post.pk).update(medical_findings=high)
        self.post.refresh_from_db()
        self.assertEqual(self.post.medical_findings, high)

    def test_unsupported_reset_method_redirects_without_unannotated_cover_lookup(self):
        from django.urls import reverse
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from users.helpers.tokens import reset_password_token
        FilePost.objects.create(post=self.post, header_image='synthetic/cover.jpg')
        response = self.client.put(reverse('users:reset_password_confirm', args=[urlsafe_base64_encode(force_bytes(self.user.pk)), reset_password_token.make_token(self.user)]))
        self.assertEqual(response.status_code, 302)
