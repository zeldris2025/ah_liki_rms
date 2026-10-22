"""Email notifications through Microsoft 365 (Microsoft Graph), sent from a mailbox in your tenant.

Needs an Azure app registration with the *application* permission Mail.Send (admin consent granted)
and a client secret; see settings.OFFICE365 and .env.example. When the settings are missing, nothing
is sent and orders are simply marked "Not configured".

Send a test email with:  python manage.py office365 test --to you@yourcompany.com
"""
import html
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.db import transaction

log = logging.getLogger(__name__)

LOGIN_URL = 'https://login.microsoftonline.com'
GRAPH_URL = 'https://graph.microsoft.com/v1.0'

_token = {'value': None, 'expires': 0}
_token_lock = threading.Lock()


class Office365Error(Exception):
    pass


def _config():
    return getattr(settings, 'OFFICE365', {})


RECIPIENT_SETTINGS = {'order': 'ORDER_EMAILS', 'issue': 'ISSUE_EMAILS', 'whatsapp_alert': 'WHATSAPP_ALERT_EMAILS'}


def recipients(kind):
    """Addresses for 'order', 'issue' or 'whatsapp_alert' emails, from the comma-separated setting."""
    raw = _config().get(RECIPIENT_SETTINGS[kind], '')
    return [a.strip() for a in raw.replace(';', ',').split(',') if a.strip()]


def is_configured(kind=None):
    c = _config()
    ready = all(c.get(k) for k in ('TENANT_ID', 'CLIENT_ID', 'CLIENT_SECRET', 'SENDER'))
    return ready and (kind is None or bool(recipients(kind)))


def _request(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        # Microsoft explains the problem in the body, e.g. "invalid_client" or "ErrorAccessDenied"
        try:
            detail = json.loads(exc.read().decode())
            err = detail.get('error')
            msg = detail.get('error_description') or (err.get('message') if isinstance(err, dict) else err)
        except (ValueError, OSError):
            msg = None
        raise Office365Error(f'HTTP {exc.code}: {(msg or exc.reason)}'.split('\r\n')[0][:200]) from exc


def access_token():
    """App-only token for Microsoft Graph, reused until shortly before it expires."""
    with _token_lock:
        if _token['value'] and time.time() < _token['expires'] - 60:
            return _token['value']
        c = _config()
        data = urllib.parse.urlencode({
            'client_id': c['CLIENT_ID'], 'client_secret': c['CLIENT_SECRET'],
            'scope': 'https://graph.microsoft.com/.default', 'grant_type': 'client_credentials',
        }).encode()
        result = _request(f"{LOGIN_URL}/{c['TENANT_ID']}/oauth2/v2.0/token", data,
                          {'Content-Type': 'application/x-www-form-urlencoded'})
        _token['value'] = result['access_token']
        _token['expires'] = time.time() + int(result.get('expires_in', 3600))
        return _token['value']


def send_mail(to, subject, body_html, sender=None):
    """Send an HTML email from a mailbox in the tenant: `sender` (e.g. the person who booked a car), or the
    configured OFFICE365_SENDER. Mail.Send as an application permission can send from any mailbox.
    Raises Office365Error with Microsoft's reason."""
    sender = sender or _config()['SENDER']
    payload = {'message': {
        'subject': subject,
        'body': {'contentType': 'HTML', 'content': body_html},
        'toRecipients': [{'emailAddress': {'address': a}} for a in to],
    }, 'saveToSentItems': True}
    _request(f'{GRAPH_URL}/users/{urllib.parse.quote(sender)}/sendMail', json.dumps(payload).encode(),
             {'Content-Type': 'application/json', 'Authorization': f'Bearer {access_token()}'})


# ── Email bodies ───────────────────────────────────────────────────────────────

_STYLE = ('font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#0F172A')


def _page(title, rows_html, url, button):
    e = html.escape
    return (f'<div style="{_STYLE}"><h2 style="margin:0 0 12px;font-size:18px">{e(title)}</h2>{rows_html}'
            f'<p style="margin:18px 0 0"><a href="{e(url)}" style="background:#0F172A;color:#fff;padding:9px 16px;'
            f'border-radius:8px;text-decoration:none;font-weight:600">{e(button)}</a></p>'
            f'<p style="color:#64748B;font-size:12px;margin-top:18px">Ah Liki Investment Corp System</p></div>')


def _details(pairs):
    e = html.escape
    cells = ''.join(f'<tr><td style="padding:3px 14px 3px 0;color:#64748B">{e(k)}</td><td style="padding:3px 0">{e(str(v))}</td></tr>'
                    for k, v in pairs if v)
    return f'<table style="border-collapse:collapse;margin-bottom:12px">{cells}</table>'


def _order_summary(order):
    """The order's details and product table, as HTML."""
    e = html.escape
    shop = order.shop
    items = list(order.items.select_related('product'))
    lines = ''.join(
        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #E2E8F0">{i.quantity} ×</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #E2E8F0">{e(i.product.name)}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #E2E8F0;text-align:right">'
        f'{"—" if i.line_total is None else f"{i.line_total:,.2f}"}</td></tr>' for i in items)
    unpriced = any(i.unit_price is None for i in items)
    total = (f'<tr><td></td><td style="padding:8px 10px;font-weight:700">Total</td><td style="padding:8px 10px;text-align:right;'
             f'font-weight:700">WST {order.total:,.2f}{" + unpriced" if unpriced else ""}</td></tr>')
    table = (f'<table style="border-collapse:collapse;border:1px solid #E2E8F0;min-width:420px">'
             f'<tr style="background:#F8FAFC"><th style="padding:6px 10px;text-align:left">Qty</th><th style="padding:6px 10px;text-align:left">'
             f'Product</th><th style="padding:6px 10px;text-align:right">WST</th></tr>{lines}{total}</table>')
    details = _details([
        ('Shop', shop.name + (f' ({shop.territory})' if shop.territory else '')),
        ('Address', order.address), ('Phone', order.phone),
        ('Placed by', order.placed_by.get_full_name() or order.placed_by.username),
        ('Notes', order.notes),
    ])
    return details + table


def order_email(order, url):
    subject = f'New FE order {order.number} — {order.shop.name}'
    return subject, _page(f'🛒 New FE order {order.number}', _order_summary(order), url, 'Open the order')


def whatsapp_failed_email(order, url, reason, retry_at):
    """Tell staff an order didn't reach the WhatsApp group, so someone can pass it on by hand."""
    e = html.escape
    if retry_at:
        from django.utils import timezone
        when = timezone.localtime(retry_at).strftime('%I:%M %p').lstrip('0')
        nxt = f'The system will keep trying every 5 minutes (next try {e(when)}) and the order page will show “Sent” once it goes through.'
    else:
        nxt = 'The system has stopped trying for this order. Use “Resend to WhatsApp” on the order page, or pass it on by hand.'
    note = (f'<p style="background:#FEF2F2;border-left:3px solid #DC2626;padding:10px 12px;margin:0 0 14px">'
            f'<b>This order didn’t reach the FE orders WhatsApp group.</b><br>Reason: {e(reason)}<br>{nxt}</p>')
    subject = f'⚠ WhatsApp failed: FE order {order.number} — {order.shop.name}'
    return subject, _page(f'⚠️ WhatsApp message failed for {order.number}', note + _order_summary(order), url, 'Open the order')


def issue_email(issue, url):
    details = _details([
        ('Type', issue.category), ('Shop', issue.shop.name if issue.shop else ''),
        ('Reported by', issue.reported_by.get_full_name() or issue.reported_by.username),
        ('Photo', 'Attached in the system' if issue.photo else ''),
    ])
    body = f'<p style="white-space:pre-line;background:#F8FAFC;border-left:3px solid #F59E0B;padding:10px 12px">{html.escape(issue.description)}</p>'
    subject = f'New FE issue: {issue.category}' + (f' — {issue.shop.name}' if issue.shop else '')
    return subject, _page(f'⚠️ New FE issue: {issue.category}', details + body, url, 'Open the issues list')


# ── Sending in the background ─────────────────────────────────────────────────

def _send_later(model, pk, subject, body, to, label, sender=None):
    """Mark the record 'Sending', then send after the database commit without holding up the page.
    If `sender`'s mailbox refuses (e.g. the address isn't a mailbox in the tenant), it goes from OFFICE365_SENDER instead."""
    model.objects.filter(pk=pk).update(email_status='Sending')

    def send():
        try:
            try:
                send_mail(to, subject, body, sender)
                status = 'Sent' + (f' from {sender}' if sender else '')
            except Office365Error as exc:
                if not sender or sender.lower() == _config()['SENDER'].lower():
                    raise
                log.warning('Office 365 email for %s could not be sent from %s (%s); using the shared mailbox', label, sender, exc)
                send_mail(to, subject, body)
                status = f'Sent from {_config()["SENDER"]} ({sender}: {exc})'
        except (Office365Error, urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.exception('Office 365 email for %s failed', label)
            status = f'Failed: {exc}'
        status = status[:120]
        model.objects.filter(pk=pk).update(email_status=status)

    transaction.on_commit(lambda: threading.Thread(target=send, daemon=True).start())


def notify_new_order(order, url):
    from .models import Order
    if not is_configured('order'):
        Order.objects.filter(pk=order.pk).update(email_status='Not configured')
        return
    subject, body = order_email(order, url)
    _send_later(Order, order.pk, subject, body, recipients('order'), order.number)


def notify_new_issue(issue, url):
    from .models import Issue
    if not is_configured('issue'):
        Issue.objects.filter(pk=issue.pk).update(email_status='Not configured')
        return
    subject, body = issue_email(issue, url)
    _send_later(Issue, issue.pk, subject, body, recipients('issue'), f'issue {issue.pk}')
