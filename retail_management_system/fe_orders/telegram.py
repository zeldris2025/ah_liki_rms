"""Post new FE orders to a Telegram group through a Telegram bot (official Bot API, free).

Create the bot with @BotFather, add it to the orders group, then put the token and
the group's chat ID in .env (see settings.TELEGRAM). When they're missing, orders
still save and are simply marked "Not configured".

Find the group's chat ID with:  python manage.py telegram chats
Send a test message:            python manage.py telegram test
"""
import html
import json
import logging
import threading
import urllib.error
import urllib.request

from django.conf import settings
from django.db import transaction

log = logging.getLogger(__name__)

API_URL = 'https://api.telegram.org'


class TelegramError(Exception):
    pass


def _config():
    return getattr(settings, 'TELEGRAM', {})


def is_configured(require_chat=True):
    c = _config()
    return bool(c.get('BOT_TOKEN') and (c.get('CHAT_ID') or not require_chat))


def call(method, payload=None):
    """Call a Bot API method and return its result. Raises TelegramError with Telegram's reason."""
    url = f"{API_URL}/bot{_config()['BOT_TOKEN']}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode() or 'null')
    except urllib.error.HTTPError as exc:
        # Telegram explains the problem in the body, e.g. "Bad Request: chat not found"
        try:
            body = json.loads(exc.read().decode())
        except (ValueError, OSError):
            raise TelegramError(f'HTTP {exc.code}') from exc
    if not body or not body.get('ok'):
        raise TelegramError((body or {}).get('description') or 'Unknown Telegram error')
    return body.get('result')


def send_to_group(text):
    return call('sendMessage', {'chat_id': _config()['CHAT_ID'], 'text': text,
                                'parse_mode': 'HTML', 'disable_web_page_preview': True})


def order_message(order, url):
    e = html.escape
    shop = order.shop
    lines = [f'🛒 <b>New FE order {e(order.number)}</b>', '',
             f'<b>Shop:</b> {e(shop.name)}' + (f' ({e(shop.territory)})' if shop.territory else '')]
    if order.address:
        lines.append(f'<b>Address:</b> {e(order.address)}')
    if order.phone:
        lines.append(f'<b>Phone:</b> {e(order.phone)}')
    lines.append(f'<b>Placed by:</b> {e(order.placed_by.get_full_name() or order.placed_by.username)}')
    lines.append('')
    for item in order.items.select_related('product'):
        lines.append(f'• {item.quantity} × {e(item.product.name)}')
    lines.append('')
    lines.append(f'<b>Total:</b> WST {order.total:,.2f}' + ('' if all(i.unit_price is not None for i in order.items.all())
                                                            else ' (+ unpriced items)'))
    if order.notes:
        lines.append(f'<b>Notes:</b> {e(order.notes)}')
    lines.append(e(url))
    return '\n'.join(lines)


def notify_new_order(order, url):
    """Queue the group message once the order is committed, without blocking the request."""
    from .models import Order
    if not is_configured():
        Order.objects.filter(pk=order.pk).update(telegram_status='Not configured')
        return
    text = order_message(order, url)
    Order.objects.filter(pk=order.pk).update(telegram_status='Sending')

    def send():
        try:
            send_to_group(text)
            status = 'Sent'
        except (TelegramError, urllib.error.URLError, OSError, ValueError) as exc:
            log.exception('Telegram notification for %s failed', order.number)
            status = f'Failed: {exc}'[:120]
        Order.objects.filter(pk=order.pk).update(telegram_status=status)

    transaction.on_commit(lambda: threading.Thread(target=send, daemon=True).start())
