"""Sites sales: our own sites (ALW HQ, ALW Savaii, …), their monthly totals from a CSV upload, and the
targets entered on the Corporate Targets page. Shown at the bottom of the All streams slide on Corporate Sales.

The upload is safe to repeat with the same file: each row is matched to a site by its Site Name (ignoring
capitals, spaces and punctuation, and with or without the "ALW" in front), and one total per site per month
is kept, so uploading a month again replaces its total instead of adding to it.
"""
import re
from datetime import date
from decimal import InvalidOperation

from django.db import transaction
from django.db.models import Sum

from .client_import import (ImportFileError, finish, log, money, new_result, parse_money, parse_month, read_rows, skip)
from .corporate import MONTH_LABELS, month_span
from .models import Site, SiteSales, SiteTarget

SITE_COLUMNS = [
    ('site',  'Site Name'),
    ('month', 'Month'),
    ('sales', 'Total Sales'),
]
SITE_ALIASES = {
    'site':  ['site', 'sitename', 'branch', 'store', 'location'],
    'month': ['period', 'salesmonth', 'date'],
    'sales': ['sales', 'amount', 'total', 'salesamount', 'salestotal'],
}


def _site_key(text):
    """'ALW Savai'i' and 'Savaii' → 'savaii'"""
    key = re.sub(r'[^a-z0-9]', '', (text or '').lower())
    return re.sub(r'^(alw|ahlikiwholesale)', '', key) or key


def site_lookup():
    sites = {}
    for s in Site.objects.all():
        sites.setdefault(_site_key(s.name), s)
    return sites


def import_site_sales(uploaded):
    present, rows = read_rows(uploaded, SITE_COLUMNS, SITE_ALIASES)
    missing = [h for f, h in SITE_COLUMNS if f not in present]
    if missing:
        raise ImportFileError(f'The file needs these columns: {", ".join(missing)}. Download the template to see the format.')

    sites = site_lookup()
    result = new_result(combined=0)
    totals, lines = {}, {}   # (site, month) → the file's total, and the rows behind it
    with transaction.atomic():
        for number, row in rows:
            name = row.get('site', '')
            site = sites.get(_site_key(name)) if name else None
            if site is None:
                known = ', '.join(s.name for s in sites.values())
                skip(result, number, name, f'“{name}” is not one of our sites ({known}).' if name else 'Site Name is missing.')
                continue
            try:
                month = parse_month(row.get('month', ''))
            except ValueError as exc:
                skip(result, number, name, str(exc))
                continue
            try:
                amount = parse_money(row.get('sales', ''))
            except (InvalidOperation, ValueError):
                skip(result, number, name, f'Total Sales "{row.get("sales", "")}" is not a number.')
                continue
            # a site listed more than once for a month is added up, not overwritten by its last row
            key = (site, month)
            if key in totals:
                result['combined'] += 1
            totals[key] = totals.get(key, 0) + amount
            lines.setdefault(key, []).append(number)

        for (site, month), amount in totals.items():
            numbers = lines[site, month]
            item = f'{site.name} · {month:%b %Y}'
            combined = f' (rows {", ".join(map(str, numbers))} added together)' if len(numbers) > 1 else ''
            record = SiteSales.objects.filter(site=site, month=month).first()
            if record is None:
                SiteSales.objects.create(site=site, month=month, sales=amount)
                result['created'] += 1
                log(result, 'added', numbers, item, f'Sales {money(amount)}{combined}')
            elif record.sales != amount:
                log(result, 'updated', numbers, item, f'Sales {money(record.sales)} → {money(amount)}{combined}')
                record.sales = amount
                record.save(update_fields=['sales', 'updated_at'])
                result['updated'] += 1
            else:
                result['unchanged'] += 1
                log(result, 'unchanged', numbers, item, f'Sales {money(amount)}{combined}')
    return finish(result)


def monthly(model, field, year, sites):
    """{site id: [12 values or None]} for SiteSales or SiteTarget."""
    values = {s.id: [None] * 12 for s in sites}
    for r in model.objects.filter(month__year=year, site__in=sites).values('site_id', 'month').annotate(total=Sum(field)):
        values[r['site_id']][r['month'].month - 1] = r['total']
    return values


def _row(site, actual, target):
    variance = actual - target if target else None
    return {'name': site.name, 'color': site.color, 'actual': actual, 'target': target, 'variance': variance,
            'variance_pct': round(variance / target * 100, 1) if target else None}


def _table(rows):
    # a site without a target still adds its sales to the total, but not to the variance
    target = sum(r['target'] or 0 for r in rows) or None
    variance = sum(r['variance'] for r in rows if r['variance'] is not None) if target else None
    return rows, {'actual': sum(r['actual'] for r in rows), 'target': target, 'variance': variance,
                  'variance_pct': round(variance / target * 100, 1) if target else None,
                  'untargeted': [r['name'] for r in rows if not r['target']]}


def year_summary(year, today=None):
    """Monthly actual and target per site for the graph, and tables of target against actual for year to date,
    the current month and each past month. Like the streams, year to date only counts months that have a target
    (for a site with at least one)."""
    today = today or date.today()
    current_month = today.month if today.year == year else (12 if year < today.year else 0)
    sites = list(Site.objects.filter(active=True))
    actual, target = monthly(SiteSales, 'sales', year, sites), monthly(SiteTarget, 'amount', year, sites)
    previous = monthly(SiteSales, 'sales', year - 1, sites)   # last year's same months, for the Sites Sales tab
    done = range(current_month)

    ytd_rows, missing = [], []
    for s in sites:
        targeted = [i for i in done if target[s.id][i] is not None]
        months = targeted or list(done)
        ytd_rows.append(_row(s, sum(actual[s.id][i] or 0 for i in months), sum(target[s.id][i] for i in targeted) or None))
        if targeted and len(targeted) < len(done):
            missing.append(f'{s.name} ({month_span([i for i in done if i not in targeted])})')

    tables = []
    if current_month:
        i = current_month - 1
        label = f'{MONTH_LABELS[i]} {year}'
        rows, tot = _table(ytd_rows)
        tables.append({'key': 'ytd', 'label': f'Year to date · {month_span(list(done))}', 'rows': rows, 'total': tot})
        rows, tot = _table([_row(s, actual[s.id][i] or 0, target[s.id][i]) for s in sites])
        tables.append({'key': 'month', 'label': label, 'rows': rows, 'total': tot})
        for i in reversed(range(current_month - 1)):   # finished months, latest first, for the past month dropdown
            rows, tot = _table([_row(s, actual[s.id][i] or 0, target[s.id][i]) for s in sites])
            tables.append({'key': f'm{i + 1}', 'label': f'{MONTH_LABELS[i]} {year}', 'rows': rows, 'total': tot, 'past': True})

    def num(v):
        return float(v) if v is not None else None

    def total(values):
        values = [v for v in values if v is not None]
        return float(sum(values)) if values else None

    return {
        'sites': sites,
        'tables': tables,
        'has_past': any(t.get('past') for t in tables),
        'missing': missing,
        'has_data': any(v is not None for s in sites for v in actual[s.id] + target[s.id]),
        'chart': {'sites': [{'name': s.name, 'color': s.color, 'actual': [num(v) for v in actual[s.id]],
                             'target': [num(v) for v in target[s.id]],
                             'previous': [num(v) for v in previous[s.id]]} for s in sites],
                  'target': [total(target[s.id][i] for s in sites) for i in range(12)],
                  'monthIndex': current_month - 1},   # the latest month that has started, -1 before the year
    }
