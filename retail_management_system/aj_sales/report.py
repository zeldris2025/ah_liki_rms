"""The numbers behind the Product QTY Sales pages: QTY sold per product this year against a comparison year (last year by default).

Every page compares like with like. By default that's the year to date: January up to the latest month with sales in
the chosen year, against the same months of the comparison year. A full year or a single month can be picked too.
The search and product filters apply to both years, and the CSV exports show exactly what's on screen.
"""
from datetime import date

from django.db.models import Max, Q, Sum

from .models import QtyProductGroup, QtySales, QtyTarget

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def years():
    """Years with sales, newest first (this year when there are none yet)."""
    return sorted({d.year for d in QtySales.objects.dates('month', 'year')}, reverse=True) or [date.today().year]


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_filters(params):
    """?year=2026&compare=2025&period=ytd|full|1..12&q=…&product=CODE&group=ID"""
    known = years()
    year = _int(params.get('year'), known[0])
    compare = _int(params.get('compare'), year - 1)
    if compare == year:
        compare = year - 1
    period = params.get('period', 'ytd')
    if period not in ('ytd', 'full') and not (period.isdigit() and 1 <= int(period) <= 12):
        period = 'ytd'
    latest = QtySales.objects.filter(month__year=year).aggregate(m=Max('month'))['m']
    through = latest.month if latest else 12
    if period == 'ytd':
        months = list(range(1, through + 1))
    elif period == 'full':
        months = list(range(1, 13))
    else:
        months = [int(period)]
    return {'year': year, 'compare': compare, 'period': period, 'months': months, 'through': through,
            'years': known, 'compare_years': sorted(set(known + [year - 1]) - {year}, reverse=True),
            'q': params.get('q', '').strip(), 'product': params.get('product', '').strip(),
            'group': QtyProductGroup.objects.filter(pk=params.get('group')).first()
                     if str(params.get('group', '')).isdigit() else None}


def period_label(f):
    if f['period'] == 'full':
        return 'Full year'
    if f['period'] == 'ytd':
        return f'Jan – {MONTHS[f["through"] - 1]}' if f['through'] > 1 else 'Jan'
    return date(2000, f['months'][0], 1).strftime('%B')


def scope(f):
    """Rows matching the search and the picked product or group, in any year."""
    qs = QtySales.objects.all()
    if f['group']:
        qs = qs.filter(f['group'].match())
    if f['q']:
        qs = qs.filter(Q(product_name__icontains=f['q']) | Q(product_code__iexact=f['q']))
    if f['product']:
        qs = qs.filter(product_code__iexact=f['product'])
    return qs


def in_period(qs, f, year):
    return qs.filter(month__year=year, month__month__in=f['months'])


def total(qs):
    return qs.aggregate(t=Sum('qty'))['t'] or 0


def change(now, before):
    """{'n': difference, 'pct': % change or None (nothing to compare with), 'dir': up|down|flat}"""
    n = now - before
    return {'n': n, 'pct': round(float(n) / float(before) * 100, 1) if before else None,
            'dir': 'up' if n > 0 else 'down' if n < 0 else 'flat'}


def monthly(qs, year):
    """QTY for each month of a year: 12 numbers (None for months with no rows)."""
    by_month = {m: t for m, t in qs.filter(month__year=year).values_list('month__month').annotate(t=Sum('qty'))}
    return [by_month.get(m) for m in range(1, 13)]


def cumulative(series, upto=12):
    out, running = [], 0
    for v in series[:upto]:
        running += v or 0
        out.append(running)
    return out


def product_names(qs=None):
    """{product code: its latest name}"""
    names = {}
    for code, name in (QtySales.objects.all() if qs is None else qs).exclude(product_name='').order_by('month').values_list(
            'product_code', 'product_name'):
        names[code] = name
    return names


def compare_rows(qs, f):
    """One row per product: QTY in the period this year and in the comparison year, the change and its share of
    this year's total. Largest this year first."""
    now = dict(in_period(qs, f, f['year']).values_list('product_code').annotate(t=Sum('qty')))
    before = dict(in_period(qs, f, f['compare']).values_list('product_code').annotate(t=Sum('qty')))
    names = product_names(qs)
    grand = sum(now.values()) or 0
    rows = []
    for code in set(now) | set(before):
        this, last = now.get(code) or 0, before.get(code) or 0
        rows.append({'code': code, 'name': names.get(code) or code, 'this': this, 'last': last,
                     'change': change(this, last),
                     'share': round(float(this) / float(grand) * 100, 1) if grand else 0,
                     'is_new': not last and this > 0, 'is_lost': not this and last > 0})
    rows.sort(key=lambda r: (-r['this'], -r['last'], r['name']))
    return rows


SORTS = {
    'this':   lambda r: -r['this'],
    'last':   lambda r: -r['last'],
    'change': lambda r: -r['change']['n'],
    'drop':   lambda r: r['change']['n'],
    'pct':    lambda r: -(r['change']['pct'] if r['change']['pct'] is not None else float('inf')),
    'name':   lambda r: r['name'].lower(),
}


def summary(qs, f, rows):
    """The headline figures for the period: both years' totals, the change, and how many products grew."""
    this, last = total(in_period(qs, f, f['year'])), total(in_period(qs, f, f['compare']))
    return {'this': this, 'last': last, 'change': change(this, last), 'biggest': max(this, last) or 1,
            'products': sum(1 for r in rows if r['this']),
            'up': sum(1 for r in rows if r['change']['dir'] == 'up'),
            'down': sum(1 for r in rows if r['change']['dir'] == 'down')}


def _num(v):
    return float(v) if v is not None else None


def trend(qs, f):
    """The chart on top of Product QTY: the products in view (a quick link's product or group, the search, or all of
    them) month by month in both years, plus the targets set by hand for that group or product, if any."""
    target = [None] * 12
    if f['group'] or f['product']:
        who = {'group': f['group']} if f['group'] else {'product_code': f['product'].upper()}
        for t in QtyTarget.objects.filter(month__year=f['year'], **who):
            target[t.month.month - 1] = float(t.qty)
    if f['group']:
        title = f['group'].name
    elif f['product']:
        title = product_names(qs).get(f['product'].upper()) or f['product'].upper()
    else:
        title = f'Products matching “{f["q"]}”' if f['q'] else 'All products'
    return {'title': title, 'year': f['year'], 'compare': f['compare'],
            'this': [_num(v) for v in monthly(qs, f['year'])], 'last': [_num(v) for v in monthly(qs, f['compare'])],
            'target': target, 'has_target': any(v is not None for v in target)}


def chart_data(qs, f, rows, top=10, movers=8):
    """Everything the charts draw, as plain numbers for json_script."""
    this, last = monthly(qs, f['year']), monthly(qs, f['compare'])
    through = f['through'] if f['period'] == 'ytd' else 12
    biggest = rows[:top]
    gainers = sorted((r for r in rows if r['change']['n'] > 0), key=lambda r: -r['change']['n'])[:movers]
    losers = sorted((r for r in rows if r['change']['n'] < 0), key=lambda r: r['change']['n'])[:movers]
    swing = gainers + losers[::-1]
    return {
        'year': f['year'], 'compare': f['compare'], 'months': MONTHS, 'picked': f['months'],
        'monthly': {'this': [_num(v) for v in this], 'last': [_num(v) for v in last]},
        'cumulative': {'this': [_num(v) for v in cumulative(this, through)],
                       'last': [_num(v) for v in cumulative(last, 12)]},
        'top': {'labels': [r['name'] for r in biggest], 'this': [_num(r['this']) for r in biggest],
                'last': [_num(r['last']) for r in biggest]},
        'movers': {'labels': [r['name'] for r in swing], 'values': [_num(r['change']['n']) for r in swing]},
    }
