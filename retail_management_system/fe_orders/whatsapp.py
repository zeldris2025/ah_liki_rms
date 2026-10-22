"""Post new FE orders to a WhatsApp group through WAHA (self-hosted WhatsApp HTTP API).

WAHA runs in its own container with a WhatsApp number logged in (scan the QR code in its
dashboard). Put its address, API key, session and the group's chat ID in .env (see
settings.WHATSAPP). When they're missing, orders still save and are simply marked "Not configured".

A message that fails is tried again every 5 minutes (for up to a day) by
    python manage.py whatsapp retry --loop
which runs as the 'notifier' service in docker-compose.yml.

Find the group's chat ID with:  python manage.py whatsapp groups
Send a test message:            python manage.py whatsapp test
"""
import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

log = logging.getLogger(__name__)

RETRY_AFTER = timedelta(minutes=5)
GIVE_UP_AFTER = timedelta(days=1)   # orders older than this stop retrying; the order page can still resend


class WhatsAppError(Exception):
    pass


def _config():
    return getattr(settings, 'WHATSAPP', {})


def is_configured(require_chat=True):
    c = _config()
    return bool(c.get('URL') and (c.get('CHAT_ID') or not require_chat))


def call(method, path, payload=None):
    """Call a WAHA endpoint and return its JSON. Raises WhatsAppError with WAHA's reason."""
    c = _config()
    url = c['URL'].rstrip('/') + path
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if c.get('API_KEY'):
        headers['X-Api-Key'] = c['API_KEY']
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode() or 'null')
    except urllib.error.HTTPError as exc:
        # WAHA explains the problem in the body, e.g. {"message": "Session \"default\" does not exist"}
        try:
            body = json.loads(exc.read().decode())
            reason = body.get('message') or body.get('error') or body
        except (ValueError, OSError, AttributeError):
            reason = None
        if exc.code == 401:
            reason = 'Unauthorized: check WAHA_API_KEY'
        raise WhatsAppError(f'HTTP {exc.code}' + (f': {reason}' if reason else '')) from exc


def send_to_group(text):
    c = _config()
    return call('POST', '/api/sendText', {'session': c.get('SESSION') or 'default',
                                          'chatId': c['CHAT_ID'], 'text': text, 'linkPreview': False})


def groups():
    """(chat ID, name) for every group the logged-in number is in."""
    session = _config().get('SESSION') or 'default'
    result = call('GET', f'/api/{session}/groups') or []
    # The shape differs between WAHA engines: a list (WEBJS) or a dict keyed by chat ID (NOWEB/GOWS)
    items = result.values() if isinstance(result, dict) else result
    found = []
    for g in items:
        gid = g.get('id') or g.get('JID')
        if isinstance(gid, dict):
            gid = gid.get('_serialized')
        name = g.get('name') or g.get('subject') or g.get('Name') or (g.get('groupMetadata') or {}).get('subject')
        if gid:
            found.append((gid, name or '(no name)'))
    return found


def _wa(text):
    """WhatsApp has no escaping, so stop customer text from switching formatting on and off."""
    return str(text).replace('*', '').replace('_', ' ').replace('~', '').replace('`', "'")


def order_message(order, url):
    shop = order.shop
    lines = [f'🛒 *New FE order {_wa(order.number)}*', '',
             f'*Shop:* {_wa(shop.name)}' + (f' ({_wa(shop.territory)})' if shop.territory else '')]
    if order.address:
        lines.append(f'*Address:* {_wa(order.address)}')
    if order.phone:
        lines.append(f'*Phone:* {_wa(order.phone)}')
    lines.append(f'*Placed by:* {_wa(order.placed_by.get_full_name() or order.placed_by.username)}')
    lines.append('')
    for item in order.items.select_related('product'):
        lines.append(f'• {item.quantity} × {_wa(item.product.name)}')
    lines.append('')
    # lines.append(f'*Total:* WST {order.total:,.2f}' + ('' if all(i.unit_price is not None for i in order.items.all())
    #                                                    else ' (+ unpriced items)'))
    if order.notes:
        lines.append(f'*Notes:* {_wa(order.notes)}')
    lines.append(url)
    return '\n'.join(lines)


def deliver(order, text, url):
    """Send now and record the result. A failure is tried again in RETRY_AFTER, until the order is a day old,
    and staff are emailed once about it (not on every retry)."""
    from .models import Order
    try:
        send_to_group(text)
    except (WhatsAppError, urllib.error.URLError, OSError, ValueError) as exc:
        log.exception('WhatsApp notification for %s failed', order.number)
        retry_at = timezone.now() + RETRY_AFTER
        if retry_at - order.created_at >= GIVE_UP_AFTER:
            retry_at = None
        Order.objects.filter(pk=order.pk).update(whatsapp_status=f'Failed: {exc}'[:120], whatsapp_retry_at=retry_at)
        alert_failure(order, url, str(exc), retry_at)
        return False
    Order.objects.filter(pk=order.pk).update(whatsapp_status='Sent', whatsapp_retry_at=None, whatsapp_alerted_at=None)
    return True


def alert_failure(order, url, reason, retry_at):
    """Email the WhatsApp alert list, once per order until its message goes through."""
    from . import office365
    from .models import Order
    if not office365.is_configured('whatsapp_alert'):
        return
    # Claim the alert first, so the page's send and the notifier never both email about the same order
    if not Order.objects.filter(pk=order.pk, whatsapp_alerted_at__isnull=True).update(whatsapp_alerted_at=timezone.now()):
        return
    try:
        subject, body = office365.whatsapp_failed_email(order, url, reason, retry_at)
        office365.send_mail(office365.recipients('whatsapp_alert'), subject, body)
    except (office365.Office365Error, urllib.error.URLError, OSError, ValueError, KeyError):
        log.exception('WhatsApp failure alert email for %s failed', order.number)
        Order.objects.filter(pk=order.pk).update(whatsapp_alerted_at=None)   # try the email again on the next retry


def notify_new_order(order, url):
    """Queue the group message once the order is committed, without blocking the request."""
    from .models import Order
    if not is_configured():
        Order.objects.filter(pk=order.pk).update(whatsapp_status='Not configured', whatsapp_retry_at=None)
        return
    text = order_message(order, url)
    # The retry time is set before sending too, so a send cut off by a restart is picked up again
    Order.objects.filter(pk=order.pk).update(whatsapp_status='Sending', whatsapp_retry_at=timezone.now() + RETRY_AFTER)
    transaction.on_commit(lambda: threading.Thread(target=deliver, args=(order, text, url), daemon=True).start())


def retry_due():
    """Try again every order whose message failed (or got stuck sending) and is due. Returns (sent, failed)."""
    from .models import Order
    if not is_configured():
        return 0, 0
    sent = failed = 0
    due = Order.objects.filter(whatsapp_retry_at__lte=timezone.now()).select_related('shop', 'placed_by')
    for order in due:
        url = settings.SITE_URL.rstrip('/') + reverse('fe_order_detail', args=[order.pk])
        if deliver(order, order_message(order, url), url):
            sent += 1
        else:
            failed += 1
    return sent, failed
