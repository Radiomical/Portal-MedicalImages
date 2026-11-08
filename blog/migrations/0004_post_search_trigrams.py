"""PostgreSQL-only expression indexes matching Django icontains SQL.

Extension creation needs database-owner permission at deployment. No extension
is removed on reversal because other applications may also use it.
"""
from django.db import migrations


INDEXES = {
    'post_title_upper_trgm': 'UPPER(title::text)',
    'post_content_upper_trgm': 'UPPER(content)',
}


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
        for name, expression in INDEXES.items():
            # A failed concurrent build can leave an invalid index. Do not
            # silently regard IF NOT EXISTS as a successful retry.
            cursor.execute('SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(%s)', [name])
            row = cursor.fetchone()
            if row:
                if not row[0]:
                    raise RuntimeError(f'{name} is invalid; inspect and remove it before retrying migration.')
                continue
            cursor.execute(f'CREATE INDEX CONCURRENTLY {name} ON blog_post USING gin ({expression} gin_trgm_ops)')


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        for name in INDEXES:
            cursor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')


class Migration(migrations.Migration):
    atomic = False
    dependencies = [('blog', '0003_post_post_recent_idx')]
    operations = [migrations.RunPython(create_indexes, drop_indexes, atomic=False)]
