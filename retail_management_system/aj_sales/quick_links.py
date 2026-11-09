"""Quick links on Product QTY: pinned products and product groups, each with one month's QTY against its target.

Works like the Product Sales quick links, in units. The target is the QTY set by hand for that month on the targets
page, otherwise the same month of the comparison year (last year by default). Green is target reached, orange is
70–99% of it, red is below.
"""
from datetime import date

from django.db.models import Max, Sum

from shops.product_sales import CLOSE_PCT, short_money, sort_quick_links, target_status  # noqa: F401 (re-exported)

from .models import QtyPinnedProduct, QtyProductGroup, QtySales, QtyTarget
from .report import MONTHS


def current_month(year):
    """Index (0–11) of the latest month in `year` with QTY uploaded, or -1."""
    latest = QtySales.objects.filter(month__year=year).aggregate(m=Max('month'))['m']
    return latest.month - 1 if latest else -1


def link_month(year, requested=''):
    """Index (0–11) of the month the quick links are measured on: the one picked (?lm=1–12), otherwise this month
    for this year (even before its QTY is uploaded), otherwise the latest month uploaded for that year, or -1."""
    if str(requested).isdigit() and 1 <= int(requested) <= 12:
        return int(requested) - 1
    today = date.today()
    if year == today.year:
        return today.month - 1
    return current_month(year)


def _pct(now, before):
    return round(float((now - before) / before * 100), 1) if before else None


def _figures(rows, year, compare, month, manual=None):
    """This month's QTY against its target, the year-to-date change and a 12-month sparkline."""
    this, last = [None] * 12, [None] * 12
    for r in rows.filter(month__year__in=[year, compare]).values('month').annotate(t=Sum('qty')):
        (this if r['month'].year == year else last)[r['month'].month - 1] = r['t']
    total = sum(v or 0 for v in this[:month + 1])
    before = sum(v or 0 for v in last[:month + 1])
    actual = (this[month] or 0) if month >= 0 else None
    manual = manual or {}
    is_manual = month in manual
    target = manual[month] if is_manual else (last[month] if month >= 0 else None)
    pct, status = target_status(actual, target)
    return {'total': total, 'growth': _pct(total, before), 'month_qty': actual, 'target': target,
            'manual_target': is_manual, 'target_short': short_money(target), 'pct': pct, 'status': status,
            'spark': [float(v) if v is not None else None for v in this]}


def _names(codes):
    return dict(QtySales.objects.filter(product_code__in=codes).values('product_code')
                .annotate(n=Max('product_name')).values_list('product_code', 'n'))


def product_links(year, compare, month):
    codes = list(QtyPinnedProduct.objects.values_list('product_code', flat=True))
    if not codes:
        return []
    names = _names(codes)
    manual = {}
    for t in QtyTarget.objects.filter(product_code__in=codes, month__year=year):
        manual.setdefault(t.product_code, {})[t.month.month - 1] = t.qty
    return [{'code': code, 'name': names.get(code) or code,
             **_figures(QtySales.objects.filter(product_code=code), year, compare, month, manual.get(code))}
            for code in codes]


def group_links(year, compare, month):
    manual = {}
    for t in QtyTarget.objects.filter(group__isnull=False, month__year=year):
        manual.setdefault(t.group_id, {})[t.month.month - 1] = t.qty
    links = []
    for g in QtyProductGroup.objects.all():
        rows = QtySales.objects.filter(g.match())
        links.append({'id': g.id, 'name': g.name, 'products': rows.values('product_code').distinct().count(),
                      **_figures(rows, year, compare, month, manual.get(g.id))})
    return links


def panel(f, requested_month=''):
    """Everything the quick links panel shows, for the year and comparison year in the page filters."""
    month = link_month(f['year'], requested_month)
    links = sort_quick_links(group_links(f['year'], f['compare'], month),
                             product_links(f['year'], f['compare'], month))
    counts = {s: sum(1 for q in links if q['status'] == s) for s in ('good', 'close', 'behind')}
    return {
        'links': links, 'counts': counts, 'close_pct': CLOSE_PCT, 'month_i': month + 1,
        'month_label': f'{MONTHS[month]} {f["year"]}' if month >= 0 else '',
        'target_label': f'{MONTHS[month]} {f["compare"]}' if month >= 0 else '',
        'uploaded': month >= 0 and QtySales.objects.filter(month__year=f['year'], month__month=month + 1).exists(),
        'month_choices': list(enumerate(MONTHS, start=1)),
        'pinned': set(QtyPinnedProduct.objects.values_list('product_code', flat=True)),
    }


def target_grid(year):
    """Rows for the targets page: every group and pinned product, with this year's targets set by hand and last
    year's monthly QTY (the target used when a month is left blank)."""
    def last_year(rows):
        out = [None] * 12
        for r in rows.filter(month__year=year - 1).values('month').annotate(t=Sum('qty')):
            out[r['month'].month - 1] = r['t']
        return out

    def cells(prefix, manual, auto):
        return [{'name': f'{prefix}_{i + 1}', 'label': MONTHS[i], 'value': manual.get(i, ''), 'auto': auto[i]}
                for i in range(12)]

    manual = {}
    for t in QtyTarget.objects.filter(month__year=year):
        key = f'g{t.group_id}' if t.group_id else f'p{t.product_code}'
        manual.setdefault(key, {})[t.month.month - 1] = t.qty
    rows = [{'kind': 'group', 'label': g.name, 'sub': 'Group', 'key': g,
             'cells': cells(f'g{g.id}', manual.get(f'g{g.id}', {}), last_year(QtySales.objects.filter(g.match())))}
            for g in QtyProductGroup.objects.all()]
    codes = list(QtyPinnedProduct.objects.values_list('product_code', flat=True))
    names = _names(codes)
    for code in codes:
        rows.append({'kind': 'product', 'label': names.get(code) or code, 'sub': code, 'key': code,
                     'cells': cells(f'p{code}', manual.get(f'p{code}', {}),
                                    last_year(QtySales.objects.filter(product_code=code)))})
    return rows


def group_members(group):
    """Products in a group (code, latest name, all-time QTY), biggest first, for the group form."""
    return list(QtySales.objects.filter(group.match()).values('product_code')
                .annotate(name=Max('product_name'), total=Sum('qty')).order_by('-total'))
