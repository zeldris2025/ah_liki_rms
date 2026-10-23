from django.core.management.base import BaseCommand, CommandError

from fe_orders import office365


class Command(BaseCommand):
    help = 'Microsoft 365 email: check the settings, or send a test email.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['check', 'test'])
        parser.add_argument('--to', help='Address for the test email (default: the order recipients)')

    def handle(self, *args, action, to=None, **opts):
        if not office365.is_configured():
            config = office365._config()
            missing = [f'OFFICE365_{k}' for k in ('TENANT_ID', 'CLIENT_ID', 'CLIENT_SECRET', 'SENDER') if not config.get(k)]
            raise CommandError(f"Missing: {', '.join(missing)}. Set them in .env, or on Azure under App Service → "
                               'Environment variables → App settings (Apply, then open a new SSH session).')
        try:
            office365.access_token()
        except (office365.Office365Error, OSError) as exc:
            raise CommandError(f'Could not sign in to Microsoft 365: {exc}\n'
                               'Check the tenant ID, client ID and that the secret VALUE (not its ID) is used.')
        self.stdout.write(self.style.SUCCESS('Signed in to Microsoft 365.'))
        self.stdout.write(f"Order emails go to: {', '.join(office365.recipients('order')) or '(nobody yet)'}")
        self.stdout.write(f"Issue emails go to: {', '.join(office365.recipients('issue')) or '(nobody yet)'}")
        if action == 'check':
            return
        to = [a.strip() for a in (to or '').split(',') if a.strip()] or office365.recipients('order')
        if not to:
            raise CommandError('Give an address with --to, or set OFFICE365_ORDER_EMAILS.')
        try:
            office365.send_mail(to, 'Ah Liki SMS — test email',
                                '<p>✅ Microsoft 365 email is connected. FE orders and issues will be emailed from this mailbox.</p>')
        except (office365.Office365Error, OSError) as exc:
            raise CommandError(f'Sending failed: {exc}\n'
                               'If it says Access Denied, grant the app the Mail.Send application permission '
                               'with admin consent, and check the sender mailbox exists.')
        self.stdout.write(self.style.SUCCESS(f"Test email sent to {', '.join(to)}."))
