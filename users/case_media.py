"""Explicit legacy-to-normalized projection. Never reads storage or signs URLs.

Run only against a quiescent source. This does not activate normalized readers,
validate object existence, infer anatomy or prove clinical publication approval.
"""
import hashlib
import json
from django.db import transaction
from .models import Case, Series, Image, FilePost
from blog.models import Post

PLANES = ('axial', 'coronal', 'sagital')
METADATA = ('format', 'accepted_data_use', 'cie_11_tagging', 'interested_region', 'other_interested_region', 'category')
FIELDS = ('id', 'header_image') + METADATA + tuple(field for plane in PLANES for field in (plane + '_images', plane + '_description'))


def projection(post):
    rows = list(FilePost.objects.filter(post=post).order_by('pk').values(*FIELDS))
    raw = {'post_id': post.pk, 'category': post.category, 'files': rows}
    fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    # Keep conflicting legacy values, including NULL/blank, instead of silently
    # choosing consent, tags, cover or category from an arbitrary slice.
    metadata = {field: list(dict.fromkeys(row[field] for row in rows)) for field in METADATA}
    metadata['cover_keys'] = list(dict.fromkeys(row['header_image'] for row in rows if row['header_image']))
    images, descriptions = {}, {}
    for plane in ('cover',) + PLANES:
        result = []
        seen = set()
        for row in rows:
            key = row['header_image'] if plane == 'cover' else row[plane + '_images']
            if not key or (plane == 'cover' and key in seen):
                continue
            seen.add(key)
            description = None if plane == 'cover' else row[plane + '_description']
            result.append({'position': len(result), 'object_key': key, 'legacy_file_id': row['id'], 'legacy_description': description})
        if result:
            images[plane] = result
            descriptions[plane] = next((item['legacy_description'] for item in result if item['legacy_description'] not in (None, '', 'None')), '')
    return {'fingerprint': fingerprint, 'metadata': metadata, 'cover_key': metadata['cover_keys'][0] if metadata['cover_keys'] else '', 'images': images, 'descriptions': descriptions}


def verify_case(case, plan):
    if (case.source_sha256 != plan['fingerprint'] or case.legacy_metadata != plan['metadata'] or case.cover_key != plan['cover_key']):
        raise ValueError('Source or case projection changed; reconciliation is required.')
    series = {item.plane: item for item in case.series.all()}
    if set(series) != set(plan['images']):
        raise ValueError('Series projection does not match legacy source.')
    for plane, expected in plan['images'].items():
        item = series[plane]
        if item.description != plan['descriptions'][plane] or item.order_basis != 'legacy_pk':
            raise ValueError('Series metadata differs from the legacy projection.')
        actual = list(item.images.order_by('position').values('position', 'object_key', 'legacy_file_id', 'legacy_description'))
        if actual != expected:
            raise ValueError('Image references or positions differ from the legacy source.')
    return True


@transaction.atomic
def backfill_case(post_id):
    post = Post.objects.select_for_update().get(pk=post_id)
    plan = projection(post)
    existing = Case.objects.filter(pk=post_id).first()
    if existing:
        verify_case(existing, plan)
        return False
    case = Case.objects.create(post=post, cover_key=plan['cover_key'], legacy_metadata=plan['metadata'], source_sha256=plan['fingerprint'])
    for plane, rows in plan['images'].items():
        series = Series.objects.create(case=case, plane=plane, description=plan['descriptions'][plane])
        Image.objects.bulk_create([Image(series=series, **row) for row in rows], batch_size=500)
    verify_case(case, plan)
    return True
