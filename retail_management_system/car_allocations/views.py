import calendar
import functools
from datetime import datetime, timedelta

from django.conf import settings

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_GET, require_POST

from shops.access import MANAGER, roles_of

from . import notify
from .models import CARS, Booking, Notification

MAX_DAYS = 31   # longest single booking


def office_time(view):
    """Run the view in the office's time zone, so typed times, 'now' and the week all match the clock on the wall."""
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        with timezone.override(settings.CAR_TIME_ZONE):
            return view(request, *args, **kwargs)
    return wrapped


def _local(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')


def _parse(value):
    """'2026-10-01T09:30' from a datetime-local input, read as office time."""
    dt = parse_datetime(value or '')
    if dt is None:
        return None
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def _can_change(user, booking):
    """Your own bookings you can edit or cancel; anyone else's only a Manager (or admin) can."""
    return booking.booked_by_id == user.pk or MANAGER in roles_of(user)


NOT_YOURS = "This is someone else's booking. Only the person who booked it, or a Manager, can change it."


def _json(booking, user):
    return {
        'id': booking.pk, 'car': booking.car, 'start': _local(booking.start), 'end': _local(booking.end),
        'reason': booking.reason, 'booked_by': booking.booked_by_name,
        'mine': booking.booked_by_id == user.pk, 'can_change': _can_change(user, booking),
    }


@login_required
@office_time
def car_allocations(request):
    year = timezone.localdate().year
    return render(request, 'car_allocations/car_allocations.html', {
        'cars': CARS,
        'months': list(enumerate(calendar.month_name))[1:],
        'years': range(year - 1, year + 3),
        'me': request.user.get_full_name() or request.user.username,
    })


@login_required
@office_time
@require_GET
def car_bookings(request):
    """Every car's bookings that overlap ?days= days (default a week) from ?start=YYYY-MM-DD,
    plus whether each car is out right now and when it's next booked."""
    day = parse_date(request.GET.get('start', '')) or timezone.localdate()
    try:
        days = min(max(int(request.GET.get('days', 7)), 1), MAX_DAYS + 2)
    except ValueError:
        days = 7
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    end = start + timedelta(days=days)
    qs = Booking.objects.filter(start__lt=end, end__gt=start).select_related('booked_by')

    now = timezone.now()
    status = {car: {'out_until': None, 'next': None} for car in CARS}
    for b in Booking.objects.filter(end__gt=now).order_by('start'):
        s = status.get(b.car)
        if s is None:
            continue
        if b.start <= now:
            s['out_until'] = _local(b.end)
        elif not s['next']:
            s['next'] = _local(b.start)
    return JsonResponse({'bookings': [_json(b, request.user) for b in qs], 'status': status, 'now': _local(now)})


@login_required
@office_time
@require_GET
def car_booking_search(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'bookings': []})
    words = Q()
    for word in q.split():
        words &= (Q(reason__icontains=word) | Q(car__iexact=word) | Q(booked_by__username__icontains=word)
                  | Q(booked_by__first_name__icontains=word) | Q(booked_by__last_name__icontains=word))
    qs = Booking.objects.filter(words).select_related('booked_by').order_by('-start')[:50]
    return JsonResponse({'bookings': [_json(b, request.user) for b in qs]})


class _Clash(Exception):
    def __init__(self, clashes):
        self.clashes = clashes


def _read_form(post):
    """(car, start, end, reason, error) from the booking form. Only overlapping times clash, so the same
    car can be booked several times on one day."""
    car = post.get('car', '')
    start, end = _parse(post.get('start')), _parse(post.get('end'))
    reason = post.get('reason', '').strip()[:255]
    error = None
    if car not in CARS:
        error = 'Choose one of the cars.'
    elif not start or not end:
        error = 'Enter when the booking starts and ends.'
    elif end <= start:
        error = 'The end must be after the start.'
    elif end <= timezone.now():
        error = 'That time has already passed.'
    elif end - start > timedelta(days=MAX_DAYS):
        error = f'A booking can be at most {MAX_DAYS} days long.'
    elif not reason:
        error = 'Enter the reason for the booking.'
    return car, start, end, reason, error


def _save_without_clash(booking, user):
    """Save, then look for clashes and roll back if there are any. Writing first locks the table,
    so two people taking the same slot at the same moment can't both get through.
    Returns None when saved, or the 409 response."""
    try:
        with transaction.atomic():
            booking.save()
            clashes = list(Booking.clashes(booking.car, booking.start, booking.end, exclude_pk=booking.pk)
                           .select_related('booked_by'))
            if clashes:
                raise _Clash(clashes)
    except _Clash as exc:
        return JsonResponse({
            'error': f'{booking.car} is already booked at that time.',
            'clashes': [_json(b, user) for b in exc.clashes],
        }, status=409)
    return None


def _week_url(request, booking):
    return request.build_absolute_uri(
        reverse('car_allocations') + f'?car={booking.car}&date={timezone.localtime(booking.start):%Y-%m-%d}')


@login_required
@office_time
@require_POST
def car_book(request):
    car, start, end, reason, error = _read_form(request.POST)
    if error:
        return JsonResponse({'error': error}, status=400)
    booking = Booking(car=car, start=start, end=end, reason=reason, booked_by=request.user)
    clash = _save_without_clash(booking, request.user)
    if clash:
        return clash
    with transaction.atomic():
        notify.notify_new_booking(booking, _week_url(request, booking))
    return JsonResponse({'booking': _json(booking, request.user)})


@login_required
@office_time
@require_POST
def car_booking_edit(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related('booked_by'), pk=booking_id)
    if not _can_change(request.user, booking):
        return JsonResponse({'error': NOT_YOURS}, status=403)
    car, start, end, reason, error = _read_form(request.POST)
    if error:
        return JsonResponse({'error': error}, status=400)
    before = notify.describe(booking)
    booking.car, booking.start, booking.end, booking.reason = car, start, end, reason
    clash = _save_without_clash(booking, request.user)
    if clash:
        return clash
    notify.notify_changed(booking, before, request.user, _week_url(request, booking))
    return JsonResponse({'booking': _json(booking, request.user)})


@login_required
@office_time
@require_POST
def car_booking_cancel(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related('booked_by'), pk=booking_id)
    if not _can_change(request.user, booking):
        return JsonResponse({'error': NOT_YOURS}, status=403)
    url = _week_url(request, booking)
    notify.notify_cancelled(booking, request.user, url)
    booking.delete()
    return JsonResponse({'ok': True})


# ── Notifications (the bell on every page) ────────────────────────────────────

@login_required
@office_time
@require_GET
def notifications(request):
    mine = Notification.objects.filter(recipient=request.user)
    return JsonResponse({
        'unread': mine.filter(read=False).count(),
        'items': [{'id': n.pk, 'message': n.message, 'link': n.link, 'read': n.read,
                   'created': timezone.localtime(n.created_at).isoformat()} for n in mine[:20]],
    })


@login_required
@office_time
@require_POST
def notifications_read(request):
    mine = Notification.objects.filter(recipient=request.user, read=False)
    if request.POST.get('id'):
        mine = mine.filter(pk=request.POST['id'])
    mine.update(read=True)
    return JsonResponse({'ok': True})
