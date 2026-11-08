from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from blog.models import Post
from users.models import Case
from users.case_media import backfill_case, projection, verify_case


class Command(BaseCommand):
    help = 'Dry-run or verify additive case media projections. No storage access; source must be quiescent.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--verify', action='store_true')
        parser.add_argument('--expected-database')
        parser.add_argument('--quiescent-source', action='store_true')

    def handle(self, *args, **options):
        if options['apply'] and options['verify']:
            raise CommandError('Choose apply or verify, not both.')
        if options['apply'] and (not options['quiescent_source'] or options['expected_database'] != str(settings.DATABASES['default']['NAME'])):
            raise CommandError('Apply requires --quiescent-source and an exact --expected-database match. These guards are not deployment authorization.')
        counts = {'cases': 0, 'series': 0, 'images': 0, 'created': 0, 'conflicted_cases': 0}
        for post in Post.objects.order_by('pk').iterator(chunk_size=100):
            plan = projection(post)
            counts['cases'] += 1
            counts['series'] += len(plan['images'])
            counts['images'] += sum(map(len, plan['images'].values()))
            counts['conflicted_cases'] += int(any(len(v) > 1 for v in plan['metadata'].values()))
            try:
                if options['apply']:
                    counts['created'] += int(backfill_case(post.pk))
                elif options['verify']:
                    verify_case(Case.objects.get(pk=post.pk), plan)
            except (ValueError, Case.DoesNotExist) as error:
                raise CommandError('Projection mismatch. Stop and reconcile before using normalized readers.') from error
        self.stdout.write(str(counts))
