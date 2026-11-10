"""Email each new application to the people in the portal settings (Microsoft 365, through fe_orders.office365).

It goes from the portal's 'send applications from' mailbox (falling back to OFFICE365_SENDER if that mailbox refuses),
with the CV, cover letter and qualifications attached. Over 3 MB together, attaching needs the Mail.ReadWrite
permission as well as Mail.Send; without it the email still goes, with every file that fits attached and the others
named (HR can always download them from the applications page).
"""
import logging
import mimetypes
import threading
import urllib.error

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from fe_orders import office365

from .models import ExpressionOfInterest, PortalSettings

log = logging.getLogger(__name__)


def _attachments(app):
    """(name, content type, bytes) for each file the applicant uploaded."""
    out = []
    for _, label, f in app.attachments():
        ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
        name = f'{app.full_name} - {label}' + (f'.{ext}' if ext else '')
        with f.open('rb') as handle:
            out.append((name, mimetypes.guess_type(name)[0] or 'application/octet-stream', handle.read()))
    return out


def _fitting(files):
    """The files that fit in one plain email (smallest first, so as many as possible), and the ones left over."""
    kept, left, total = [], [], 0
    for f in sorted(files, key=lambda f: len(f[2])):
        if total + len(f[2]) <= office365.MAX_ATTACHMENTS_BYTES:
            kept.append(f)
            total += len(f[2])
        else:
            left.append(f)
    order = [f[0] for f in files]
    return sorted(kept, key=lambda f: order.index(f[0])), sorted(left, key=lambda f: order.index(f[0]))


def application_email(app, url, not_attached=()):
    role = app.role
    rows = [('Position', f'{app.role_title} ({role.get_position_type_display()})' if role else app.role_title),
            ('Company', role.place if role else ''), ('Name', app.full_name), ('Age', app.age), ('Village', app.village),
            ('Email', app.email), ('Phone', app.phone), ('Experience (highest qualification)', app.highest_qualification),
            ('Received', timezone.localtime(app.created_at).strftime('%d %b %Y, %I:%M %p'))]
    files = [label for _, label, _ in app.attachments()]
    if files:
        rows.append(('Attachments', ', '.join(files)))
    if not_attached:
        rows.append(('Not attached (too large)', ', '.join(not_attached) + ': download from the applications page'))
    subject = f'New application: {app.role_title} — {app.full_name}'
    return subject, office365._page(f'📨 New application for {app.role_title}', office365._details(rows), url,
                                    'Open the applications')


def _send(app_pk, to, sender, attempts):
    """Try each (subject, body, files) in turn, from `sender` and then from the system mailbox, until one goes."""
    errors = []
    system = office365._config().get('SENDER', '').lower()
    mailboxes = [None] if not sender or sender.lower() == system else [sender, None]
    for subject, body, files, note in attempts:
        for frm in mailboxes:
            try:
                office365.send_mail(to, subject, body, frm, files)
            except (office365.Office365Error, urllib.error.URLError, OSError, ValueError, KeyError) as exc:
                errors.append(f'{frm or "system mailbox"}: {exc}')
                log.warning('Application %s email from %s failed: %s', app_pk, frm or 'system mailbox', exc)
                continue
            status = f'Sent from {frm or office365._config()["SENDER"]}' + (f' with {len(files)} file{"s" * (len(files) != 1)}' if files else '')
            if note:
                status += f'; {note}'
            if errors:
                status += f' (after: {errors[0]})'
            ExpressionOfInterest.objects.filter(pk=app_pk).update(email_status=status[:120])
            return
    ExpressionOfInterest.objects.filter(pk=app_pk).update(email_status=f'Failed: {errors[-1]}'[:120])


def notify_new_application(app):
    portal = PortalSettings.load()
    to = portal.application_email_list
    if not (office365.is_configured() and to):
        ExpressionOfInterest.objects.filter(pk=app.pk).update(email_status='Not configured')
        return
    url = settings.SITE_URL.rstrip('/') + (reverse('hr_applications', args=[app.role_id]) if app.role_id
                                           else reverse('hr_vacancies'))
    files = _attachments(app)
    subject, body = application_email(app, url)
    attempts = [(subject, body, files, '')]
    kept, left = _fitting(files)
    if left:   # if Microsoft won't take the big upload, still send what fits and name the rest
        labels = [name.split(' - ', 1)[-1].rsplit('.', 1)[0] for name, _, _ in left]
        attempts.append((subject, application_email(app, url, labels)[1], kept, f'not attached: {", ".join(labels)}'))
    ExpressionOfInterest.objects.filter(pk=app.pk).update(email_status='Sending')
    sender = portal.application_sender or None
    transaction.on_commit(lambda: threading.Thread(target=_send, args=(app.pk, to, sender, attempts), daemon=True).start())
