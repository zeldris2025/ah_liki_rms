from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from fe_orders import sales_export


class Command(BaseCommand):
    help = ('Write the daily FE sales file(s) to settings.SALES_EXPORT_DIR. '
            'Files are also updated automatically as orders come in; use this to catch up past days.')

    def add_arguments(self, parser):
        parser.add_argument('--date', dest='day', help='Day to export, YYYY-MM-DD (default: today)')
        parser.add_argument('--days', type=int, default=1, help='How many days back from --date to export (default: 1)')

    def handle(self, *args, day=None, days=1, **opts):
        try:
            last = date.fromisoformat(day) if day else date.today()
        except ValueError:
            raise CommandError('Use --date YYYY-MM-DD, e.g. --date 2026-09-29')
        for n in range(max(days, 1)):
            d = last - timedelta(days=n)
            path = sales_export.save_daily_file(d)
            lines = sales_export.items_between(d, d).count()
            self.stdout.write(f'{d}: {lines} line{"s" if lines != 1 else ""} → {path}')
