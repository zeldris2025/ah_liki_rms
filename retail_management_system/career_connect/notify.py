"""Email each new application to the people in the portal settings (Microsoft 365, through fe_orders.office365).

It goes from the portal's 'send applications from' mailbox (falling back to OFFICE365_SENDER if that mailbox refuses),
with the CV, cover letter and qualifications attached while they fit in one email; otherwise the email lists them
and links to the HR applications page, where they can always be downloaded.
"""
import mimetypes

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from fe_orders import office365

from .models import ExpressionOfInterest, PortalSettings


def _attachments(app):
    """(name, content type, bytes) for each file, or None when together they are too big for one email."""
    files = app.attachments()
    if sum(f.size for _, _, f in files) > office365.MAX_ATTACHMENTS_BYTES:
        return None
    out = []
    for _, label, f in files:
        ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
        name = f'{app.full_name} - {label}' + (f'.{ext}' if ext else '')
        with f.open('rb') as handle:
            out.append((name, mimetypes.guess_type(name)[0] or 'application/octet-stream', handle.read()))
    return out


def application_email(app, url, attached):
    role = app.role
    rows = [('Position', f'{app.role_title} ({role.get_position_type_display()})' if role else app.role_title),
            ('Company', role.place if role else ''), ('Name', app.full_name), ('Age', app.age), ('Village', app.village),
            ('Email', app.email), ('Phone', app.phone), ('Experience (highest qualification)', app.highest_qualification),
            ('Received', timezone.localtime(app.created_at).strftime('%d %b %Y, %I:%M %p'))]
    files = [label for _, label, _ in app.attachments()]
    if files:
        rows.append(('Attachments', ', '.join(files) + ('' if attached else
                                                     ' (too large to attach: download them from the applications page)')))
    subject = f'New application: {app.role_title} — {app.full_name}'
    return subject, office365._page(f'📨 New application for {app.role_title}', office365._details(rows), url,
                                    'Open the applications')


def notify_new_application(app):
    portal = PortalSettings.load()
    to = portal.application_email_list
    if not (office365.is_configured() and to):
        ExpressionOfInterest.objects.filter(pk=app.pk).update(email_status='Not configured')
        return
    files = _attachments(app)
    url = settings.SITE_URL.rstrip('/') + (reverse('hr_applications', args=[app.role_id]) if app.role_id
                                           else reverse('hr_vacancies'))
    subject, body = application_email(app, url, files is not None)
    office365._send_later(ExpressionOfInterest, app.pk, subject, body, to, f'application {app.pk}',
                          sender=portal.application_sender or None, attachments=files or ())
