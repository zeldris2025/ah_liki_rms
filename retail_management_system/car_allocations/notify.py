"""Tell the rest of the office when someone books a car: a notice under everyone's bell, plus an email.

Email goes through Microsoft 365 (fe_orders.office365), from the booker's own mailbox (the email address on
their account), to everyone else in Sales and Marketing, plus the Managers and admins who approve it.
The Finance cars are Finance's own: their bookings only go to the Financial Controllers (never admins or Managers).
"""
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from fe_orders import office365
from shops.access import FINANCIAL_CONTROLLER, FINANCE_ROLES, MANAGER, ROLES, SOCIAL_GROUP

FE_GROUP = 'fe_boys'   # FE staff don't get car booking emails

from .models import FINANCE_CARS, Booking, Notification


def finance_only():
    """Users at a Finance level with no office level (shops.access.is_finance)."""
    User = get_user_model()
    return User.objects.filter(groups__name__in=FINANCE_ROLES, is_superuser=False).exclude(groups__name__in=ROLES)


def controllers():
    """Active Financial Controllers: the only people who hear about and decide on the Finance cars."""
    return finance_only().filter(is_active=True, groups__name=FINANCIAL_CONTROLLER).distinct()


def team(car):
    """Who hears about a car's bookings: for a Finance car only the Financial Controllers, otherwise the active
    Sales, Marketing, Manager and Social users and admins (FE staff never book cars)."""
    if car in FINANCE_CARS:
        return controllers()
    User = get_user_model()
    return (User.objects.filter(is_active=True)
            .filter(Q(is_superuser=True) | Q(groups__name__in=ROLES + (SOCIAL_GROUP,))).distinct())


def _time(dt):
    """12-hour time, e.g. '9:30 AM'."""
    return f'{dt.hour % 12 or 12}:{dt:%M} {"AM" if dt.hour < 12 else "PM"}'


def _when(booking):
    start, end = timezone.localtime(booking.start), timezone.localtime(booking.end)
    if start.date() == end.date():
        return f'{start:%a %d %b}, {_time(start)}–{_time(end)}'
    return f'{start:%a %d %b} {_time(start)} – {end:%a %d %b} {_time(end)}'


def managers(car):
    """The people who approve or decline: the Financial Controllers for a Finance car, otherwise Managers and admins."""
    if car in FINANCE_CARS:
        return controllers()
    User = get_user_model()
    return User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(groups__name=MANAGER)).distinct()


def approver(car):
    """What the person who approves this car's bookings is called."""
    return FINANCIAL_CONTROLLER if car in FINANCE_CARS else MANAGER


def car_recipients(car, exclude_user):
    """Email addresses for a booking, but not the booker's: for a Finance car, the Financial Controllers; otherwise
    the active Sales and Marketing users, plus the Managers and admins who approve (never HR, Social or fe_boys)."""
    User = get_user_model()
    if car in FINANCE_CARS:
        users = team(car)
    else:
        users = (User.objects.filter(is_active=True)
                 .filter(Q(is_superuser=True) | Q(groups__name__in=ROLES))
                 .exclude(groups__name=FE_GROUP))
    users = users.exclude(pk=exclude_user.pk).exclude(email='')
    mine = (exclude_user.email or '').strip().lower()
    return sorted({u.email.strip() for u in users if u.email.strip().lower() != mine})


def email_link(booking):
    """The 'Open Car Allocations' button: always the office server (settings.SITE_URL), whichever
    address the booker happened to use, so it works for everyone who gets the email."""
    return (settings.SITE_URL.rstrip('/') + reverse('car_allocations')
            + f'?car={quote(booking.car)}&date={timezone.localtime(booking.start):%Y-%m-%d}')


def booking_email(booking, url):
    details = office365._details([
        ('Car', booking.car), ('When', _when(booking)), ('Reason', booking.reason),
        ('Booked by', booking.booked_by_name),
    ])
    subject = f'Car {booking.car} booked — {_when(booking)}'
    return subject, office365._page(f'🚗 Car {booking.car} booked: Requesting your kind Approval', details, url, 'Open Car Allocations')


def notify_new_booking(booking, url):
    """Everyone else hears about the booking; while it waits for approval, Managers are asked to decide."""
    message = f'{booking.booked_by_name} booked {booking.car} for {_when(booking)}: {booking.reason}'[:255]
    pending = booking.status == Booking.PENDING
    deciders = set(managers(booking.car).values_list('pk', flat=True)) if pending else set()
    ask = f'Approval needed: {booking.booked_by_name} booked {booking.car} for {_when(booking)}: {booking.reason}'[:255]
    Notification.objects.bulk_create([
        Notification(recipient=u, message=ask if u.pk in deciders else message, link=url, booking=booking)
        for u in team(booking.car).exclude(pk=booking.booked_by_id)
    ])

    to = car_recipients(booking.car, booking.booked_by)
    if not (office365.is_configured() and to):
        Booking.objects.filter(pk=booking.pk).update(email_status='Not configured')
        return
    subject, body = booking_email(booking, email_link(booking))
    office365._send_later(Booking, booking.pk, subject, body, to, f'car booking {booking.pk}',
                          sender=(booking.booked_by.email or '').strip() or None)


def notify_cancelled(booking, by_user, url):
    who = by_user.get_full_name() or by_user.username
    message = f'{who} cancelled the {booking.car} booking for {_when(booking)}'[:255]
    Notification.objects.bulk_create([
        Notification(recipient=u, message=message, link=url) for u in team(booking.car).exclude(pk=by_user.pk)
    ])


def describe(booking):
    """'81, Thu 01 Oct, 09:00–10:00', to say what a booking was before it changed."""
    return f'{booking.car}, {_when(booking)}'


def notify_changed(booking, before, by_user, url):
    """Tell everyone else about an edit. When a Manager edits someone else's booking, the owner hears it first-hand."""
    who = by_user.get_full_name() or by_user.username
    whose = 'their' if booking.booked_by_id == by_user.pk else f"{booking.booked_by_name}'s"
    after = describe(booking)
    change = f'{before} → {after}' if after != before else after
    message = f'{who} changed {whose} booking: {change}: {booking.reason}'[:255]
    notices = [Notification(recipient=u, message=message, link=url, booking=booking)
               for u in team(booking.car).exclude(pk=by_user.pk).exclude(pk=booking.booked_by_id)]
    if booking.booked_by_id != by_user.pk:
        notices.append(Notification(recipient=booking.booked_by, link=url, booking=booking,
                                    message=f'{who} ({approver(booking.car)}) changed your booking: {change}: {booking.reason}'[:255]))
    Notification.objects.bulk_create(notices)


def notify_decision(booking, manager, url):
    """Tell the booker that a Manager approved or declined their booking (bell + email, with the comment)."""
    who = manager.get_full_name() or manager.username
    approved = booking.status == Booking.APPROVED
    verb = 'approved' if approved else 'declined'
    message = f'{who} {verb} your {booking.car} booking for {_when(booking)}'
    if not approved and booking.decline_reason:
        message += f': {booking.decline_reason}'
    if booking.booked_by_id != manager.pk:
        Notification.objects.create(recipient=booking.booked_by, message=message[:255], link=url, booking=booking)

    to = (booking.booked_by.email or '').strip()
    if not (office365.is_configured() and to) or booking.booked_by_id == manager.pk:
        return
    rows = [('Car', booking.car), ('When', _when(booking)), ('Reason', booking.reason), (f'{verb.capitalize()} by', who)]
    if not approved:
        rows.append(('Comment', booking.decline_reason))
    title = f'{"✅" if approved else "❌"} Your car {booking.car} booking was {verb}'
    body = office365._page(title, office365._details(rows), email_link(booking), 'Open Car Allocations')
    office365._send_later(Booking, booking.pk, f'Car {booking.car} booking {verb} — {_when(booking)}', body, [to],
                          f'car booking {booking.pk} {verb}')
