import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from fe_orders import whatsapp


class Command(BaseCommand):
    help = ('WhatsApp (WAHA) helpers: list groups to find the chat ID, send a test message, '
            'or resend failed order messages (retry; --loop keeps checking every minute).')

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['groups', 'test', 'retry'])
        parser.add_argument('--loop', action='store_true', help='retry: keep running, checking every --every seconds')
        parser.add_argument('--every', type=int, default=60)

    def handle(self, *args, action, loop=False, every=60, **opts):
        if action == 'retry':
            return self.retry(loop, every)
        if not whatsapp.is_configured(require_chat=(action == 'test')):
            raise CommandError('Set WAHA_URL'
                               + (' and WHATSAPP_ORDERS_CHAT_ID' if action == 'test' else '')
                               + ' in .env first, then restart.')
        try:
            if action == 'groups':
                found = whatsapp.groups()
                if not found:
                    self.stdout.write('No groups found. Add the WhatsApp number logged in to WAHA to the group, '
                                      'then run this again.')
                for chat_id, name in found:
                    self.stdout.write(f'{chat_id}\t{name}')
            else:
                whatsapp.send_to_group('✅ Ah Liki FE ordering is connected. New orders will be posted here.')
                self.stdout.write(self.style.SUCCESS('Test message sent.'))
        except (whatsapp.WhatsAppError, OSError) as exc:
            raise CommandError(f'WAHA call failed: {exc}')

    def retry(self, loop, every):
        while True:
            close_old_connections()
            try:
                sent, failed = whatsapp.retry_due()
                if sent or failed:
                    self.stdout.write(f'WhatsApp retry: {sent} sent, {failed} still failing')
                    self.stdout.flush()
            except Exception:   # keep the loop alive whatever happens (database locked, WAHA down...)
                whatsapp.log.exception('WhatsApp retry run failed')
            if not loop:
                return
            time.sleep(every)
