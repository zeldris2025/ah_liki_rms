"""Manager analytics: will each corporate stream reach its target, how each rep is doing, and average sales per day.

Sales arrive as month totals (the Monthly Sales upload), so a day's average is the month's sales over the days
those figures cover. For a month still running, that's up to the day of the latest upload; a finished month
counts every day. A stream's month-end projection is its average per day so far carried to the end of the month.
"""
import calendar
from collections import defaultdict
from datetime import date

from django.db.models import Max

from . import corporate
from .models import MonthlySales, SalesTarget, Shop

AT_RISK = 0.9   # projected at 90% of target or more is "At risk"; lower is "Off track"


def add_months(month, n):
    i = month.month - 1 + n
    return date(month.year + i // 12, i % 12 + 1, 1)


def days_in(month):
    return calendar.monthrange(month.year, month.month)[1]


def days_covered(month, today=None):
    """(days the month's figures cover, days in the month). A finished month covers every day; the month
    still running covers up to the latest upload (or today, if nothing is uploaded for it yet)."""
    today = today or date.today()
    days = days_in(month)
    if today >= date(month.year, month.month, days) or today < month:
        return (days if today >= month else 0), days
    last = MonthlySales.objects.filter(month=month).aggregate(u=Max('updated_at'))['u']
    as_of = last.astimezone().date() if last else today   # this computer's clock, like the dashboard
    return min(max(as_of, month), today).day, days


def available_months(today=None):
    """Months with uploaded sales, newest first, never later than this month."""
    today = today or date.today()
    this = date(today.year, today.month, 1)
    return list(MonthlySales.objects.filter(month__lte=this).dates('month', 'month', order='DESC'))


def _pct(new, old):
    return round((new - old) / old * 100, 1) if old else None


def _status(actual, target, projected, covered, days):
    if not target:
        return 'none', 'No target'
    if actual >= target:
        return 'reached', 'Reached'
    if covered >= days:
        return 'missed', 'Missed'
    if not covered:
        return 'none', 'Not started'
    if projected >= target:
        return 'on', 'On track'
    if projected >= target * AT_RISK:
        return 'risk', 'At risk'
    return 'off', 'Off track'


def month_analysis(month, today=None):
    """Everything on the Analytics page for one month (the first of the month)."""
    today = today or date.today()
    covered, days = days_covered(month, today)
    prev, last_year = add_months(month, -1), date(month.year - 1, month.month, 1)
    prev_days = days_in(prev)

    # One pass over every sale from January last year up to the month: {shop: {month: sales}}
    sales = defaultdict(dict)
    for shop_id, m, amount in (MonthlySales.objects.filter(month__gte=date(month.year - 1, 1, 1), month__lte=month)
                               .values_list('shop_id', 'month', 'sales')):
        sales[shop_id][m] = sales[shop_id].get(m, 0) + float(amount)

    shops = {pk: (name, (territory or '').strip()) for pk, name, territory in
             Shop.objects.values_list('id', 'name', 'territory')}
    ids, _, _ = corporate.client_ids_by_manager()
    reps = corporate.managers()
    owner = {pk: r['key'] for r in reps for pk in ids[r['key']]}
    rep_by_key = {r['key']: r for r in reps}

    def total(shop_ids, m):
        return sum(sales[pk].get(m, 0) for pk in shop_ids if pk in sales)

    def active(shop_ids, m):
        return sum(1 for pk in shop_ids if sales.get(pk, {}).get(m, 0) > 0)

    def ytd(shop_ids, year, upto):
        months = [date(year, i, 1) for i in range(1, upto + 1)]
        return sum(total(shop_ids, m) for m in months)

    # Days so far this year (to the end of the figures) and over the same span last year, for a fair YTD per day
    ytd_days = sum(days_in(date(month.year, i, 1)) for i in range(1, month.month)) + covered
    ly_ytd_days = sum(days_in(date(month.year - 1, i, 1)) for i in range(1, month.month + 1))

    targets = {t.manager: float(t.amount) for t in SalesTarget.objects.filter(month=month)}

    def figures(shop_ids, target):
        actual = total(shop_ids, month)
        per_day = actual / covered if covered else 0
        projected = per_day * days if covered < days else actual
        prev_day = total(shop_ids, prev) / prev_days
        ly_day = total(shop_ids, last_year) / days
        this_ytd, ly_ytd = ytd(shop_ids, month.year, month.month), ytd(shop_ids, month.year - 1, month.month)
        n_active = active(shop_ids, month)
        left = days - covered
        status, label = _status(actual, target, projected, covered, days)
        return {
            'clients': len(shop_ids), 'active': n_active, 'actual': actual, 'per_day': per_day,
            'per_client': actual / n_active if n_active else 0,
            'prev_per_day': prev_day, 'vs_prev': _pct(per_day, prev_day) if covered else None,
            'ly_per_day': ly_day, 'vs_ly': _pct(per_day, ly_day) if covered else None,
            'ytd': this_ytd, 'ytd_per_day': this_ytd / ytd_days if ytd_days else 0,
            'vs_ly_ytd': _pct(this_ytd / ytd_days, ly_ytd / ly_ytd_days) if ytd_days and ly_ytd else None,
            'target': target, 'projected': projected,
            'pct_so_far': round(actual / target * 100) if target else None,
            'pct_projected': round(projected / target * 100) if target else None,
            # where they'd be today if the target were spread evenly over the month
            'expected_by_now': target * covered / days if target else None,
            'gap': projected - target if target else None,
            'needed_per_day': max(target - actual, 0) / left if target and left else None,
            'status': status, 'status_label': label,
        }

    streams = []
    for r in reps:
        row = figures(ids[r['key']], targets.get(r['key']))
        streams.append({'key': r['key'], 'name': r['name'], 'color': r['color'], 'streams': r['streams'], **row})
    corp_ids = [pk for r in reps for pk in ids[r['key']]]
    corp_target = sum(s['target'] for s in streams if s['target']) or None
    corporate_total = {'name': 'All corporate streams', **figures(corp_ids, corp_target)}
    for s in streams:
        s['share'] = round(s['actual'] / corporate_total['actual'] * 100, 1) if corporate_total['actual'] else None

    for s in streams + [corporate_total]:
        # the target check's bar: sales so far, the projection, and markers at the target and where they should be by now
        scale = max(s['target'] or 0, s['projected'], s['actual']) or 1
        s['bar'] = {'actual': round(s['actual'] / scale * 100, 1), 'projected': round(s['projected'] / scale * 100, 1),
                    'target': round(s['target'] / scale * 100, 1) if s['target'] else None,
                    'expected': round(s['expected_by_now'] / scale * 100, 1) if s['target'] else None}

    all_ids = list(shops)
    company = figures(all_ids, None)

    # Average sales per day for the 12 months to this one: every client, and each stream
    trend_months = [add_months(month, i) for i in range(-11, 1)]

    def trend(shop_ids):
        out = []
        for m in trend_months:
            n = covered if m == month else days_in(m)
            uploaded = any(m in sales[pk] for pk in shop_ids if pk in sales)   # no upload for the month: a gap, not 0
            out.append(round(total(shop_ids, m) / n, 2) if n and uploaded else None)
        return out

    trend_data = {
        'labels': [f"{corporate.MONTH_LABELS[m.month - 1]} {m:%y}" for m in trend_months],
        'all': trend(all_ids),
        'streams': [{'name': r['name'], 'color': r['color'], 'values': trend(ids[r['key']])} for r in reps],
        'partial': covered < days,
    }

    # Territories this month
    by_territory = defaultdict(list)
    for pk, (_, territory) in shops.items():
        by_territory[territory or 'No territory'].append(pk)
    territories = []
    for name, shop_ids in by_territory.items():
        actual = total(shop_ids, month)
        if not actual:
            continue
        territories.append({'name': name, 'actual': actual, 'active': active(shop_ids, month), 'clients': len(shop_ids),
                            'per_day': actual / covered if covered else 0,
                            'share': round(actual / company['actual'] * 100, 1) if company['actual'] else None,
                            'vs_prev': _pct(actual / covered, total(shop_ids, prev) / prev_days) if covered else None})
    territories.sort(key=lambda t: -t['actual'])

    def client(pk, value, **extra):
        key = owner.get(pk)
        return {'id': pk, 'name': shops.get(pk, ('?', ''))[0], 'value': value,
                'rep': rep_by_key[key]['name'] if key else '', 'color': rep_by_key[key]['color'] if key else '', **extra}

    top_clients = sorted((client(pk, s[month]) for pk, s in sales.items() if s.get(month, 0) > 0),
                         key=lambda c: -c['value'])[:10]
    # Bought last month but nothing yet this month: the biggest of them first
    quiet = sorted((client(pk, s[prev]) for pk, s in sales.items() if s.get(prev, 0) > 0 and s.get(month, 0) <= 0),
                   key=lambda c: -c['value'])
    quiet_value = sum(c['value'] for c in quiet)

    return {
        'month': month, 'prev': prev, 'last_year': last_year,
        'covered': covered, 'days': days, 'days_left': days - covered, 'in_progress': covered < days,
        'as_of': date(month.year, month.month, covered) if covered else None,
        'streams': streams, 'corporate': corporate_total, 'company': company,
        'has_targets': any(s['target'] for s in streams),
        'on_track': sum(1 for s in streams if s['status'] in ('on', 'reached')),
        'targeted': sum(1 for s in streams if s['target']),
        'trend': trend_data, 'territories': territories,
        'top_clients': top_clients, 'quiet': quiet[:10], 'quiet_count': len(quiet), 'quiet_value': quiet_value,
    }
