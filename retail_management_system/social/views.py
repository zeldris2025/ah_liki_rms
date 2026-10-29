"""Social #s: every Monday and Saturday the Social team record each company's Facebook and Instagram followers.

The Social dashboard (what the Social group see at /), the numbers table and update form, and the analytics.
Who may open these is decided in shops.access (the Social group and Managers)."""
import csv
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from . import csv_import
from .forms import SocialUpdateForm
from .models import COMPANIES, PLATFORMS, SocialCount, is_update_day, last_update_day, next_update_day, office_today

COMPANY_NAMES = dict(COMPANIES)
# Each company's colour on its cards and tabs (identity only; the charts colour by platform)
COMPANY_COLORS = {
    'ah_liki_wholesale':   ('#1D4ED8', '#DBEAFE'),
    'farmer_joe':          ('#15803D', '#DCFCE7'),
    'burger_bills':        ('#B91C1C', '#FEE2E2'),
    'natural_samoa_water': ('#0E7490', '#CFFAFE'),
    'ink_pro':             ('#6D28D9', '#EDE9FE'),
}
RANGES = [('90', 'Last 3 months'), ('180', 'Last 6 months'), ('365', 'Last 12 months'), ('all', 'All time')]


def _change(now, before):
    """How much a number moved ({'n', 'pct'}), or None when either side is missing."""
    if now is None or before is None:
        return None
    return {'n': now - before, 'pct': round((now - before) / before * 100, 1) if before else None}


def _by_company(qs):
    """{company key: [SocialCount, newest first]}"""
    grouped = {}
    for c in qs.order_by('-date'):
        grouped.setdefault(c.company, []).append(c)
    return grouped


def _summary(counts_by_company, since=None):
    """Per company: the latest numbers, the change since the update before, and (with since=date) the change since
    the last update on or before that date (or the first one after it, when there's none that old)."""
    rows = []
    for key, name in COMPANIES:
        counts = counts_by_company.get(key, [])
        latest = counts[0] if counts else None
        previous = counts[1] if len(counts) > 1 else None
        base = None
        if since and counts:
            base = next((c for c in counts if c.date <= since), counts[-1])
            if base is latest:
                base = None
        row = {'key': key, 'name': name, 'color': COMPANY_COLORS[key][0], 'soft': COMPANY_COLORS[key][1],
               'latest': latest, 'since_date': base.date if base else None, 'platforms': []}
        for platform, label in PLATFORMS:
            value = getattr(latest, platform) if latest else None
            row['platforms'].append({
                'key': platform, 'label': label, 'value': value,
                'change': _change(value, getattr(previous, platform)) if previous else None,
                'since': _change(value, getattr(base, platform)) if base else None,
            })
        rows.append(row)
    return rows


def _status(today=None):
    """The update that should be in by now, which companies it still lacks, and when the next one is due."""
    today = today or office_today()
    day = last_update_day(today)
    done = set(SocialCount.objects.filter(date=day).values_list('company', flat=True))
    return {'day': day, 'is_today': day == today, 'next': next_update_day(today),
            'missing': [name for key, name in COMPANIES if key not in done], 'done': len(done),
            'total': len(COMPANIES)}


def _previous_counts(day):
    """{company key: its last SocialCount before day}, shown beside the boxes as a guide."""
    previous = {}
    for c in SocialCount.objects.filter(date__lt=day).order_by('-date'):
        previous.setdefault(c.company, c)
    return previous


@login_required(login_url='login')
def dashboard(request):
    """What the Social group see at /: this update's progress, each company's latest numbers, and their cars."""
    from car_allocations.models import Booking
    from shops.models import Shop
    my_bookings = (Booking.objects.filter(booked_by=request.user, end__gt=timezone.now())
                   .exclude(status=Booking.DECLINED).order_by('start'))
    return render(request, 'social/dashboard.html', {
        'status': _status(),
        'companies': _summary(_by_company(SocialCount.objects.all())),
        'my_bookings': my_bookings[:5], 'booking_count': my_bookings.count(),
        'shop_count': Shop.objects.count(),
    })


@login_required(login_url='login')
def numbers(request):
    """Social #s: one company's numbers per update day (Date, Facebook, Instagram), newest first. ?company=key"""
    company = request.GET.get('company')
    if company not in COMPANY_NAMES:
        company = COMPANIES[0][0]
    counts = list(SocialCount.objects.filter(company=company).select_related('updated_by').order_by('-date'))
    rows = []
    for i, c in enumerate(counts):
        before = counts[i + 1] if i + 1 < len(counts) else None
        rows.append({'count': c, 'platforms': [
            {'value': getattr(c, p), 'change': _change(getattr(c, p), getattr(before, p)) if before else None}
            for p, _ in PLATFORMS]})
    # Changes are worked out first, so a page's last row still compares with the one on the next page
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    return render(request, 'social/numbers.html', {
        'companies': [{'key': k, 'name': n, 'color': COMPANY_COLORS[k][0]} for k, n in COMPANIES],
        'company': company, 'company_name': COMPANY_NAMES[company], 'color': COMPANY_COLORS[company],
        'rows': page, 'page_obj': page, 'count': len(rows), 'status': _status(),
    })


@login_required(login_url='login')
def update(request):
    """Record (or correct) every company's numbers for one update day. ?date=YYYY-MM-DD picks the day (the latest
    Monday or Saturday by default); ?company=key is the Social #s tab to go back to."""
    day = last_update_day()
    try:
        picked = datetime.date.fromisoformat(request.GET.get('date') or '')
        if is_update_day(picked) and picked <= office_today():
            day = picked
    except ValueError:
        pass
    company = request.POST.get('company', request.GET.get('company', ''))
    company = company if company in COMPANY_NAMES else ''

    if request.method == 'POST':
        form = SocialUpdateForm(request.POST)
        if form.is_valid():
            day = form.cleaned_data['date']
            saved = removed = 0
            with transaction.atomic():
                for key, values in form.numbers().items():
                    if all(v is None for v in values.values()):
                        removed += SocialCount.objects.filter(company=key, date=day).delete()[0]
                        continue
                    SocialCount.objects.update_or_create(company=key, date=day,
                                                         defaults={**values, 'updated_by': request.user})
                    saved += 1
            said = f'Saved the numbers for {saved} compan{"y" if saved == 1 else "ies"} on {day:%A %d %B %Y}.'
            if removed:
                said += f' Removed {removed} that {"was" if removed == 1 else "were"} cleared.'
            messages.success(request, said)
            return redirect(reverse('social_numbers') + (f'?company={company}' if company else ''))
    else:
        existing = {c.company: c for c in SocialCount.objects.filter(date=day)}
        initial = {'date': day}
        for key, _ in COMPANIES:
            for platform, _ in PLATFORMS:
                initial[f'{key}_{platform}'] = getattr(existing.get(key), platform, None)
        form = SocialUpdateForm(initial=initial)

    previous = _previous_counts(day)
    rows = [{'name': name, 'was': previous.get(key),
             'boxes': [(box, getattr(previous.get(key), platform, None)) for box, platform in
                       ((facebook, 'facebook'), (instagram, 'instagram'))]}
            for key, name, facebook, instagram in form.rows()]
    return render(request, 'social/update.html', {
        'form': form, 'day': day, 'rows': rows, 'company': company,
        'is_new': not SocialCount.objects.filter(date=day).exists(),
    })


@login_required(login_url='login')
def import_csv(request):
    """Upload Social #s from a CSV. Matches on Company + Date; see social/csv_import.py for the rules."""
    from shops.client_import import ImportFileError
    extra = {'columns': csv_import.COLUMNS, 'companies': COMPANIES}
    result = None
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            result = csv_import.import_social_numbers(request.FILES['csv_file'], request.user)
        except ImportFileError as exc:
            return render(request, 'social/import.html', {**extra, 'error': str(exc)})
    return render(request, 'social/import.html', {**extra, 'result': result})


@login_required(login_url='login')
def download_template(request):
    """The Social #s CSV template: the five companies on the latest update day."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="social_numbers_template.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in csv_import.COLUMNS])
    day = last_update_day()
    for _, name in COMPANIES:
        w.writerow([f'{day:%Y-%m-%d}', name, '', ''])
    return response


@login_required(login_url='login')
def analytics(request):
    """How each company's following has grown: Facebook and Instagram over time, and the change over the range.
    ?range=90|180|365|all (days; 180 by default)."""
    span = request.GET.get('range')
    if span not in dict(RANGES):
        span = '180'
    today = office_today()
    since = None if span == 'all' else today - datetime.timedelta(days=int(span))
    counts = SocialCount.objects.all()
    in_range = _by_company(counts.filter(date__gte=since) if since else counts)

    charts = []
    for key, name in COMPANIES:
        points = sorted(in_range.get(key, []), key=lambda c: c.date)
        charts.append({'key': key, 'name': name, 'labels': [f'{c.date:%d %b %Y}' for c in points],
                       'facebook': [c.facebook for c in points], 'instagram': [c.instagram for c in points]})
    summary = _summary(_by_company(counts), since=since or datetime.date.min)
    totals = []
    for i, (platform, label) in enumerate(PLATFORMS):
        values = [r['platforms'][i]['value'] for r in summary if r['platforms'][i]['value'] is not None]
        changes = [r['platforms'][i]['since']['n'] for r in summary if r['platforms'][i]['since']]
        totals.append({'label': label, 'value': sum(values) if values else None,
                       'change': {'n': sum(changes), 'pct': None} if changes else None})
    return render(request, 'social/analytics.html', {
        'summary': summary, 'totals': totals, 'charts': charts,
        'ranges': RANGES, 'range': span, 'range_label': dict(RANGES)[span], 'status': _status(today),
        'has_data': counts.exists(),
    })
