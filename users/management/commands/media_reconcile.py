import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from users.models import Image, OriginalDicom
from users.media_reconciliation import audit_objects


class Command(BaseCommand):
    help = 'Aggregate read-only manifest summary; explicit guarded read-back optional. Never changes DB or storage.'

    def add_arguments(self, parser):
        parser.add_argument('--read-objects', action='store_true')
        parser.add_argument('--include-originals', action='store_true')
        parser.add_argument('--expected-database')
        parser.add_argument('--expected-storage')
        parser.add_argument('--quiescent-source', action='store_true')
        parser.add_argument('--byte-budget', type=int)
        parser.add_argument('--max-object-bytes', type=int, default=32*1024*1024)

    def handle(self, *args, **options):
        if not options['read_objects']:
            result = {'display_references': Image.objects.count(), 'original_references': OriginalDicom.objects.count(), 'unknown_display_hashes': Image.objects.filter(sha256='').count(), 'objects_read': 0}
        else:
            if (not options['quiescent_source'] or options['expected_database'] != str(settings.DATABASES['default']['NAME']) or options['expected_storage'] != settings.MEDIA_STORAGE or not options['byte_budget'] or options['byte_budget'] <= 0 or options['max_object_bytes'] <= 0):
                raise CommandError('Read-back requires explicit quiescent source, exact database/storage and positive byte limits. Guards are not authorization.')
            result = audit_objects(options['byte_budget'], options['max_object_bytes'], options['include_originals'])
        self.stdout.write(json.dumps(result, sort_keys=True))
        if any(result.get(key) for key in ('missing', 'mismatch', 'read_error', 'unavailable_storage', 'unknown_baseline', 'budget_exhausted', 'budget_or_validation_error', 'conflicting_baselines')):
            raise CommandError('Audit incomplete or differences found. No state was changed. Reconcile before activation.')
