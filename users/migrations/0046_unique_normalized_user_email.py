"""Require explicit conflict resolution; never merge accounts or rewrite emails."""
from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower, Trim


NAME = 'auth_user_normalized_email_unique'


def create_unique(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    duplicates = (User.objects.using(schema_editor.connection.alias)
                  .annotate(normalized=Lower(Trim('email'))).exclude(normalized='')
                  .values('normalized').annotate(total=Count('pk')).filter(total__gt=1).count())
    if duplicates:
        raise RuntimeError(f'Normalized email collision groups: {duplicates}. Resolve owners explicitly before retrying. No accounts were modified.')
    schema_editor.execute(f"CREATE UNIQUE INDEX {NAME} ON auth_user (LOWER(TRIM(email))) WHERE TRIM(email) <> ''")


def remove_unique(apps, schema_editor):
    schema_editor.execute(f'DROP INDEX {NAME}')


class Migration(migrations.Migration):
    dependencies = [('users', '0045_filepost_filepost_category_valid_and_more'), ('auth', '0012_alter_user_first_name_max_length')]
    operations = [migrations.RunPython(create_unique, remove_unique)]
