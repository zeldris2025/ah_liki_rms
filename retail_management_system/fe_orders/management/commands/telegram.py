from django.core.management.base import BaseCommand, CommandError

from fe_orders import telegram


class Command(BaseCommand):
    help = 'Telegram bot helpers: list group chats to find the chat ID, or send a test message.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['chats', 'test'])

    def handle(self, *args, action, **opts):
        if not telegram.is_configured(require_chat=(action == 'test')):
            raise CommandError('Set TELEGRAM_BOT_TOKEN'
                               + (' and TELEGRAM_ORDERS_CHAT_ID' if action == 'test' else '')
                               + ' in .env first, then restart.')
        try:
            if action == 'chats':
                self.list_chats()
            else:
                telegram.send_to_group('✅ Ah Liki FE ordering is connected. New orders will be posted here.')
                self.stdout.write(self.style.SUCCESS('Test message sent.'))
        except (telegram.TelegramError, OSError) as exc:
            raise CommandError(f'Telegram call failed: {exc}')

    def list_chats(self):
        # The bot only learns about a group from recent activity: being added to it, or a message sent there.
        chats = {}
        for update in telegram.call('getUpdates') or []:
            for key in ('message', 'my_chat_member', 'edited_message'):
                chat = (update.get(key) or {}).get('chat') or {}
                if chat.get('type') in ('group', 'supergroup'):
                    chats[chat['id']] = chat.get('title') or '(no title)'
        if not chats:
            self.stdout.write('No groups found yet. Add the bot to the group (or remove and re-add it), '
                              'send a message like /start in the group, then run this again.')
        for chat_id, title in chats.items():
            self.stdout.write(f'{chat_id}\t{title}')
