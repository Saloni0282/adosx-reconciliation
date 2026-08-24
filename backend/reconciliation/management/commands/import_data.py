"""
Django management command: python manage.py import_data

Imports locations.csv, system_a.csv, system_b.csv from the data/ directory
(at the project root, one level above backend/), then runs reconciliation
to populate the Disagreement table.

Re-running this command is safe: all imports use update_or_create, so existing
rows are updated rather than duplicated. Disagreements are recomputed fresh.

Usage:
    python manage.py import_data
    python manage.py import_data --data-dir /path/to/csv/files
"""
import logging
from pathlib import Path

from django.core.management.base import BaseCommand

from reconciliation.services.importer import import_locations, import_system_a, import_system_b
from reconciliation.services.reconciler import run_reconciliation
from reconciliation.models import SystemBEntry

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import CSV data (locations, System A, System B) and run reconciliation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--data-dir',
            type=str,
            default=None,
            help=(
                'Path to directory containing locations.csv, system_a.csv, system_b.csv. '
                'Defaults to <project_root>/data/'
            ),
        )

    def handle(self, *args, **options):
        # Resolve data directory.
        # Default: this file is at backend/reconciliation/management/commands/import_data.py
        # parents[4] = backend/, parents[5] would be one above.
        # We want <project_root>/data/ which is one directory above backend/.
        if options['data_dir']:
            data_dir = Path(options['data_dir'])
        else:
            # backend/ is parents[4] of this file; project root is parents[4].parent
            backend_dir = Path(__file__).resolve().parents[4]
            data_dir = backend_dir.parent / 'data'

        self.stdout.write(f'Data directory: {data_dir}')

        locations_file = data_dir / 'locations.csv'
        system_a_file = data_dir / 'system_a.csv'
        system_b_file = data_dir / 'system_b.csv'

        for f in [locations_file, system_a_file, system_b_file]:
            if not f.exists():
                self.stderr.write(self.style.ERROR(f'File not found: {f}'))
                return

        self.stdout.write('Importing locations...')
        location_map = import_locations(locations_file)
        self.stdout.write(self.style.SUCCESS(f'  {len(location_map)} locations imported'))

        self.stdout.write('Importing System A records...')
        record_map = import_system_a(system_a_file, location_map)
        self.stdout.write(self.style.SUCCESS(f'  {len(record_map)} records imported'))

        self.stdout.write('Importing System B entries...')
        import_system_b(system_b_file, location_map, record_map)
        b_count = SystemBEntry.objects.count()
        self.stdout.write(self.style.SUCCESS(f'  {b_count} entries imported'))

        self.stdout.write('Running reconciliation...')
        counts = run_reconciliation()
        self.stdout.write(self.style.SUCCESS('Reconciliation complete:'))
        for reason, count in sorted(counts.items()):
            self.stdout.write(f'  {reason}: {count}')
        total = sum(counts.values())
        self.stdout.write(self.style.SUCCESS(f'  TOTAL DISAGREEMENTS: {total}'))
