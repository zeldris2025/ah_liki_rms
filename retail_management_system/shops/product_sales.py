"""Product sales: the monthly CSV upload, the numbers behind the Product Sales charts, and the Excel report.

Every chart and the table follow the same filters (search, pinned product, category, year and month
range), so what's on screen is exactly what gets exported.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from django.db.models import Max, Q, Sum

from . import client_import
from .models import CustomerProductSales, PinnedProduct, ProductGroup, ProductSales, QuickLinkTarget, Shop

COLUMNS = [
    ('product_code', 'Product Code'),
    ('product_name', 'Product Name'),
    ('month',        'Date (YY-MM)'),
    ('total_sales',  'Total Sales'),
]
ALIASES = {
    'product_code': ['code', 'productno', 'productnumber', 'itemno', 'itemcode', 'no', 'sku'],
    'product_name': ['name', 'description', 'itemname', 'product'],
    'month':        ['date', 'dateyymm', 'yymm', 'period', 'salesmonth'],
    'total_sales':  ['sales', 'totalsales', 'amount', 'total', 'salesamount', 'value'],
}
# Quick link colours: this month's sales against the same month last year (the target)
CLOSE_PCT = 70   # 70–99% of target is "almost there" (orange); below is red, 100%+ is green

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ── Upload ─────────────────────────────────────────────────────────────────────

def parse_yy_mm(value):
    """'26-09' (the file's YY-MM) → date(2026, 9, 1); other month formats like 2026-09 or Sep-26 also work."""
    m = re.fullmatch(r'\s*(\d{2})\s*[-/.]\s*(\d{1,2})\s*', value or '')
    if m and 1 <= int(m.group(2)) <= 12:
        return date(2000 + int(m.group(1)), int(m.group(2)), 1)
    return client_import.parse_month(value or '')


def import_product_sales(uploaded):
    present, rows = client_import.read_rows(uploaded, COLUMNS, ALIASES)
    missing = [h for f, h in COLUMNS if f not in present]
    if missing:
        raise client_import.ImportFileError(
            f'The file needs these columns: {", ".join(missing)}. Download the template to see the format.')

    result = {'created': 0, 'updated': 0, 'unchanged': 0, 'skipped': []}
    existing = {(r.product_code.casefold(), r.month): r for r in ProductSales.objects.all()}
    with transaction.atomic():
        for number, row in rows:
            code, name = row.get('product_code', ''), ' '.join(row.get('product_name', '').split())
            label = f'Row {number} ({code or name or "blank"})'
            if not code or not name:
                result['skipped'].append(f'{label}: Product Code and Product Name are both needed.')
                continue
            try:
                month = parse_yy_mm(row.get('month', ''))
            except ValueError:
                result['skipped'].append(f'{label}: "{row.get("month", "")}" is not a month. Use YY-MM, e.g. 26-09.')
                continue
            try:
                amount = client_import.parse_money(row.get('total_sales', ''))
            except (InvalidOperation, ValueError):
                result['skipped'].append(f'{label}: Total Sales "{row.get("total_sales", "")}" is not a number.')
                continue

            record = existing.get((code.casefold(), month))
            if record is None:
                existing[(code.casefold(), month)] = ProductSales.objects.create(
                    product_code=code, product_name=name[:255], month=month, total_sales=amount)
                result['created'] += 1
            elif record.total_sales != amount or record.product_name != name[:255]:
                record.total_sales, record.product_name = amount, name[:255]
                record.save(update_fields=['total_sales', 'product_name', 'updated_at'])
                result['updated'] += 1
            else:
                result['unchanged'] += 1
    return result


# ── Customer product sales upload (for the Top 10 products chart on Corporate Sales) ──

CUSTOMER_COLUMNS = [
    ('customer_code', 'Customer Code'),
    ('customer_name', 'Customer Name'),
    ('product_code',  'Product Code'),
    ('product_name',  'Product Name'),
    ('month',         'Date (YY-MM)'),
    ('sales',         'Sales'),
]
CUSTOMER_ALIASES = {
    'customer_code': ['customerno', 'customernumber', 'custno', 'custcode', 'accountno', 'account'],
    'customer_name': ['customer', 'client', 'clientname'],
    **ALIASES,
    'sales':         ALIASES['total_sales'],
}


def import_customer_product_sales(uploaded):
    present, rows = client_import.read_rows(uploaded, CUSTOMER_COLUMNS, CUSTOMER_ALIASES)
    missing = [h for f, h in CUSTOMER_COLUMNS if f != 'customer_name' and f not in present]
    if missing:
        raise client_import.ImportFileError(
            f'The file needs these columns: {", ".join(missing)}. Download the template to see the format.')

    shops = {s.customer_code.casefold(): s for s in Shop.objects.exclude(customer_code__isnull=True)}
    result = {'created': 0, 'updated': 0, 'unchanged': 0, 'skipped': []}
    with transaction.atomic():
        for number, row in rows:
            ccode = row.get('customer_code', '')
            code, name = row.get('product_code', ''), ' '.join(row.get('product_name', '').split())
            label = f'Row {number} ({ccode or "blank"} · {code or name or "blank"})'
            shop = shops.get(ccode.casefold()) if ccode else None
            if shop is None:
                result['skipped'].append(f'{label}: no client has Customer Code "{ccode}". Upload it in Import Clients first.'
                                         if ccode else f'{label}: Customer Code is missing.')
                continue
            if not code or not name:
                result['skipped'].append(f'{label}: Product Code and Product Name are both needed.')
                continue
            try:
                month = parse_yy_mm(row.get('month', ''))
            except ValueError:
                result['skipped'].append(f'{label}: "{row.get("month", "")}" is not a month. Use YY-MM, e.g. 26-09.')
                continue
            try:
                amount = client_import.parse_money(row.get('sales', ''))
            except (InvalidOperation, ValueError):
                result['skipped'].append(f'{label}: Sales "{row.get("sales", "")}" is not a number.')
                continue

            record, created = CustomerProductSales.objects.get_or_create(
                shop=shop, product_code=code, month=month, defaults={'product_name': name[:255], 'sales': amount})
            if created:
                result['created'] += 1
            elif record.sales != amount or record.product_name != name[:255]:
                record.sales, record.product_name = amount, name[:255]
                record.save(update_fields=['sales', 'product_name', 'updated_at'])
                result['updated'] += 1
            else:
                result['unchanged'] += 1
    return result


# ── Filters ────────────────────────────────────────────────────────────────────

def _month_param(value):
    try:
        return parse_yy_mm(value) if value else None
    except ValueError:
        return None


def read_filters(params):
    """Filters from the query string, with sensible defaults from the data."""
    years = [d.year for d in ProductSales.objects.dates('month', 'year', order='DESC')]
    latest_year = years[0] if years else date.today().year
    try:
        year = int(params.get('year') or latest_year)
    except ValueError:
        year = latest_year
    try:
        compare = int(params.get('compare') or year - 1)
    except ValueError:
        compare = year - 1
    group_id = params.get('group', '')
    group = ProductGroup.objects.filter(pk=group_id).first() if group_id.isdigit() else None
    return {
        'q': params.get('q', '').strip(),
        'tq': params.get('tq', '').strip(),   # the table's own search box; doesn't change the charts
        'product': params.get('product', '').strip(),
        'group': group,
        'category': params.get('category', '').strip(),
        'year': year, 'compare': compare, 'years': years or [year],
        'start': _month_param(params.get('from', '')),
        'end': _month_param(params.get('to', '')),
        'sort': params.get('sort', ''),
    }


def product_scope(f):
    """Sales rows for the products picked by search / quick link / category (all dates)."""
    qs = ProductSales.objects.all()
    if f['group']:
        qs = qs.filter(f['group'].match())
    if f['product']:
        qs = qs.filter(product_code__iexact=f['product'])
    if f['q']:
        qs = qs.filter(Q(product_code__icontains=f['q']) | Q(product_name__icontains=f['q']))
    if f['category']:
        from fe_orders.models import Product
        codes = list(Product.objects.filter(category=f['category']).exclude(product_no='')
                     .values_list('product_no', flat=True))
        qs = qs.filter(product_code__in=codes)
    return qs


def dated(qs, f):
    if f['start']:
        qs = qs.filter(month__gte=f['start'])
    if f['end']:
        qs = qs.filter(month__lte=f['end'])
    return qs


def categories():
    """Catalogue categories that have products with sales (products link by Product No = Product Code)."""
    from fe_orders.models import Product
    codes = set(ProductSales.objects.values_list('product_code', flat=True).distinct())
    return sorted({c for no, c in Product.objects.exclude(product_no='').values_list('product_no', 'category') if no in codes})


# ── Numbers behind the charts ─────────────────────────────────────────────────

def _by_month(qs):
    return {r['month']: r['t'] for r in qs.values('month').annotate(t=Sum('total_sales'))}


def _year_series(totals, year):
    return [totals.get(date(year, m, 1)) for m in range(1, 13)]


def _cumulative(series):
    out, running = [], Decimal(0)
    last = max((i for i, v in enumerate(series) if v is not None), default=-1)
    for i, v in enumerate(series):
        running += v or 0
        out.append(running if i <= last else None)
    return out


def current_month(year):
    """Index (0–11) of the latest month in `year` with any product sales uploaded, or -1."""
    latest = ProductSales.objects.filter(month__year=year).aggregate(m=Max('month'))['m']
    return latest.month - 1 if latest else -1


def short_money(v):
    """3025562 → '3.0M', 125076 → '125k', 1600 → '1.6k', 950 → '950'"""
    if v is None:
        return ''
    v = float(v)
    if abs(v) >= 1e6:
        return f'{v / 1e6:.1f}M'
    if abs(v) >= 1e4:
        return f'{v / 1e3:.0f}k'
    if abs(v) >= 1e3:
        return f'{v / 1e3:.1f}'.removesuffix('.0') + 'k'   # 1,600 → 1.6k, 1,000 → 1k
    return f'{v:.0f}'


def target_status(actual, target):
    """(% of target, 'good' | 'close' | 'behind' | 'none')."""
    if not target:
        return None, 'none'
    pct = round(float(actual or 0) / float(target) * 100)
    return pct, 'good' if pct >= 100 else 'close' if pct >= CLOSE_PCT else 'behind'


def _pct(now, before):
    return round(float((now - before) / before * 100), 1) if before else None


def analytics(f):
    scope = product_scope(f)
    totals = _by_month(scope)                       # every month, for the year-vs-year charts
    trend_totals = _by_month(dated(scope, f))       # the chosen date range, for the trend chart
    trend_months = sorted(trend_totals)

    this_year, last_year = _year_series(totals, f['year']), _year_series(totals, f['compare'])
    months_in = [i for i, v in enumerate(this_year) if v is not None]
    through = max(months_in) if months_in else -1   # compare the same months in both years
    ytd = sum(v or 0 for v in this_year[:through + 1])
    ytd_before = sum(v or 0 for v in last_year[:through + 1])
    best = max(((v, i) for i, v in enumerate(this_year) if v is not None), default=None)

    # Top products: for the chosen months if a range is set, otherwise the focus year
    top = (dated(scope, f).filter(**({} if (f['start'] or f['end']) else {'month__year': f['year']}))
           .values('product_code').annotate(total=Sum('total_sales'), name=Max('product_name'))
           .order_by('-total')[:10])
    top_label = 'selected months' if (f['start'] or f['end']) else str(f['year'])

    month_now, month_before = (this_year[through], last_year[through]) if through >= 0 else (None, None)
    month_pct, month_status = target_status(month_now, month_before)

    return {
        'trend': {'labels': [f'{MONTHS[m.month - 1]} {m:%y}' for m in trend_months],
                  'values': [trend_totals[m] for m in trend_months]},
        'yoy': {'labels': MONTHS, 'year': f['year'], 'compare': f['compare'], 'this': this_year, 'last': last_year},
        'cumulative': {'this': _cumulative(this_year), 'last': _cumulative(last_year)},
        'top': {'label': top_label, 'rows': list(top)},
        'kpi': {
            'ytd': ytd, 'ytd_before': ytd_before, 'growth': _pct(ytd, ytd_before),
            'through': MONTHS[through] if through >= 0 else '',
            'month_label': f'{MONTHS[through]} {f["year"]}' if through >= 0 else '',
            'month_value': month_now, 'month_before': month_before,
            'month_pct': month_pct, 'month_status': month_status,
            'best_month': f'{MONTHS[best[1]]} {f["year"]}' if best else '', 'best_value': best[0] if best else None,
            'products': scope.values('product_code').distinct().count(),
            'avg_month': ytd / len(months_in) if months_in else None,
        },
    }


def _link_figures(rows, year, compare, month, manual=None):
    """This month's sales against its target, year-to-date change, and a sparkline.
    The target is the one set by hand for this month (`manual`: {month index: amount}), otherwise the same
    month last year. `month` is the current month index (latest month uploaded), the same for every card."""
    this, last = [None] * 12, [None] * 12
    for r in rows.filter(month__year__in=[year, compare]).values('month').annotate(t=Sum('total_sales')):
        (this if r['month'].year == year else last)[r['month'].month - 1] = r['t']
    total = sum(v or 0 for v in this[:month + 1])
    before = sum(v or 0 for v in last[:month + 1])
    actual = (this[month] or 0) if month >= 0 else None
    manual = manual or {}
    is_manual = month in manual
    target = manual[month] if is_manual else (last[month] if month >= 0 else None)
    pct, status = target_status(actual, target)
    return {'total': total, 'growth': _pct(total, before), 'month_sales': actual, 'target': target, 'manual_target': is_manual,
            'target_short': short_money(target),
            'pct': pct, 'status': status, 'spark': [float(v) if v is not None else None for v in this]}


def quick_links(year, compare):
    """Pinned products with this month against target, year-to-date change, and a 12-month sparkline."""
    month = current_month(year)
    codes = list(PinnedProduct.objects.values_list('product_code', flat=True))
    if not codes:
        return []
    names = dict(ProductSales.objects.filter(product_code__in=codes).values('product_code')
                 .annotate(n=Max('product_name')).values_list('product_code', 'n'))
    manual = {}
    for t in QuickLinkTarget.objects.filter(product_code__in=codes, month__year=year):
        manual.setdefault(t.product_code, {})[t.month.month - 1] = t.amount
    return [{'code': code, 'name': names.get(code, code),
             **_link_figures(ProductSales.objects.filter(product_code=code), year, compare, month, manual.get(code))}
            for code in codes]


def group_links(year, compare):
    """Product groups with the same figures as pinned products, plus how many products they hold."""
    month = current_month(year)
    manual = {}
    for t in QuickLinkTarget.objects.filter(group__isnull=False, month__year=year):
        manual.setdefault(t.group_id, {})[t.month.month - 1] = t.amount
    links = []
    for g in ProductGroup.objects.all():
        rows = ProductSales.objects.filter(g.match())
        links.append({'id': g.id, 'name': g.name, 'products': rows.values('product_code').distinct().count(),
                      **_link_figures(rows, year, compare, month, manual.get(g.id))})
    return links


def sort_quick_links(groups, products):
    """Groups and pinned products in one list: furthest below target first, reached ones last,
    and anything without a target at the very end."""
    items = [{**g, 'kind': 'group'} for g in groups] + [{**p, 'kind': 'product'} for p in products]
    return sorted(items, key=lambda i: (i['pct'] is None, i['pct'] if i['pct'] is not None else 0, i['name'].lower()))


def target_grid(year):
    """Rows for the quick-link targets page: every group and pinned product, with this year's manual targets
    and last year's monthly sales (the automatic target used when a month is left blank)."""
    def last_year(rows):
        out = [None] * 12
        for r in rows.filter(month__year=year - 1).values('month').annotate(t=Sum('total_sales')):
            out[r['month'].month - 1] = r['t']
        return out

    def cells(prefix, manual, auto):
        return [{'name': f'{prefix}_{i + 1}', 'label': MONTHS[i], 'value': manual.get(i, ''), 'auto': auto[i]}
                for i in range(12)]

    rows = []
    manual = {}
    for t in QuickLinkTarget.objects.filter(month__year=year):
        key = f'g{t.group_id}' if t.group_id else f'p{t.product_code}'
        manual.setdefault(key, {})[t.month.month - 1] = t.amount
    for g in ProductGroup.objects.all():
        rows.append({'kind': 'group', 'label': g.name, 'sub': 'Group',
                     'cells': cells(f'g{g.id}', manual.get(f'g{g.id}', {}), last_year(ProductSales.objects.filter(g.match())))})
    codes = list(PinnedProduct.objects.values_list('product_code', flat=True))
    names = dict(ProductSales.objects.filter(product_code__in=codes).values('product_code')
                 .annotate(n=Max('product_name')).values_list('product_code', 'n'))
    for code in codes:
        rows.append({'kind': 'product', 'label': names.get(code, code), 'sub': code,
                     'cells': cells(f'p{code}', manual.get(f'p{code}', {}), last_year(ProductSales.objects.filter(product_code=code)))})
    return rows


def group_members(group):
    """Products in a group (code, latest name, all-time sales), biggest first, for the group form preview."""
    return list(ProductSales.objects.filter(group.match()).values('product_code')
                .annotate(name=Max('product_name'), total=Sum('total_sales')).order_by('-total'))


def table(f):
    qs = dated(product_scope(f), f)
    if f['tq']:
        qs = qs.filter(Q(product_code__icontains=f['tq']) | Q(product_name__icontains=f['tq']))
    order = {'sales': ['-total_sales'], 'name': ['product_name', '-month'], 'code': ['product_code', '-month'],
             'oldest': ['month', 'product_name']}.get(f['sort'], ['-month', '-total_sales'])
    return qs.order_by(*order)


# ── Excel report ───────────────────────────────────────────────────────────────

def workbook(f, only=None):
    """The whole report as .xlsx, or one sheet: only = trend | yoy | cumulative | top | data."""
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill

    a = analytics(f)
    wb = Workbook()
    wb.remove(wb.active)
    head_fill, head_font = PatternFill('solid', fgColor='0F172A'), Font(bold=True, color='FFFFFF')
    money = '#,##0.00'

    def sheet(title, headers, rows, widths):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for cell in ws[1]:
            cell.fill, cell.font, cell.alignment = head_fill, head_font, Alignment(horizontal='center')
        for r in rows:
            ws.append([float(v) if isinstance(v, Decimal) else v for v in r])
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + i)].width = w
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, float):
                    cell.number_format = money
        ws.freeze_panes = 'A2'
        return ws

    def chart(ws, kind, title, cols, rows, anchor, y_title='WST'):
        c = kind()
        c.title, c.y_axis.title, c.height, c.width = title, y_title, 9, 22
        c.add_data(Reference(ws, min_col=cols[0], max_col=cols[1], min_row=1, max_row=rows + 1), titles_from_data=True)
        c.set_categories(Reference(ws, min_col=1, min_row=2, max_row=rows + 1))
        ws.add_chart(c, anchor)

    filters = describe(f)
    if only in (None, 'summary'):
        k = a['kpi']
        ws = sheet('Summary', ['Ah Liki Wholesale — Product Sales Report', ''], [
            ['Generated', date.today().isoformat()],
            ['Filters', filters],
            [],
            [f'Sales {f["year"]} (Jan–{k["through"]})' if k['through'] else f'Sales {f["year"]}', k['ytd']],
            [f'Same months {f["compare"]}', k['ytd_before']],
            ['Change vs last year', f'{k["growth"]}%' if k['growth'] is not None else '—'],
            ['Best month', f'{k["best_month"]}: {k["best_value"]:,.2f}' if k['best_value'] is not None else '—'],
            ['Average per month', k['avg_month'] or 0],
            ['Products', k['products']],
        ], [34, 60])
        ws['A1'].alignment = Alignment(horizontal='left')
    if only in (None, 'trend'):
        ws = sheet('Monthly Trend', ['Month', 'Total Sales'], zip(a['trend']['labels'], a['trend']['values']), [14, 18])
        if a['trend']['labels']:
            chart(ws, LineChart, 'Monthly sales trend', (2, 2), len(a['trend']['labels']), 'D2')
    if only in (None, 'yoy'):
        y = a['yoy']
        ws = sheet(f'{f["year"]} vs {f["compare"]}', ['Month', str(f['year']), str(f['compare']), 'Change %'],
                   [[m, t, l, _pct(t, l) if t is not None else None] for m, t, l in zip(MONTHS, y['this'], y['last'])],
                   [10, 16, 16, 12])
        chart(ws, BarChart, f'{f["year"]} vs {f["compare"]} by month', (2, 3), 12, 'F2')
    if only in (None, 'cumulative'):
        c = a['cumulative']
        ws = sheet('Year to Date', ['Month', f'{f["year"]} running total', f'{f["compare"]} running total'],
                   zip(MONTHS, c['this'], c['last']), [10, 22, 22])
        chart(ws, LineChart, 'Running total, year to date', (2, 3), 12, 'E2')
    if only in (None, 'top'):
        rows = [[r['product_code'], r['name'], r['total']] for r in a['top']['rows']]
        ws = sheet('Top Products', ['Product Code', 'Product Name', f'Total Sales ({a["top"]["label"]})'], rows, [16, 44, 22])
        if rows:
            c = BarChart()
            c.type, c.title, c.height, c.width = 'bar', f'Top products · {a["top"]["label"]}', 9, 22
            c.add_data(Reference(ws, min_col=3, min_row=1, max_row=len(rows) + 1), titles_from_data=True)
            c.set_categories(Reference(ws, min_col=2, min_row=2, max_row=len(rows) + 1))
            ws.add_chart(c, 'E2')
    if only in (None, 'data'):
        sheet('Data', ['Product Code', 'Product Name', 'Date (YY-MM)', 'Total Sales'],
              ([r.product_code, r.product_name, f'{r.month:%y-%m}', r.total_sales] for r in table(f).iterator()),
              [16, 44, 14, 18])

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def describe(f):
    parts = []
    if f['group']:
        parts.append(f'group {f["group"].name}')
    if f['product']:
        parts.append(f'product {f["product"]}')
    if f['q']:
        parts.append(f'search "{f["q"]}"')
    if f['tq']:
        parts.append(f'table search "{f["tq"]}"')
    if f['category']:
        parts.append(f'category {f["category"]}')
    if f['start'] or f['end']:
        parts.append(f'months {f["start"]:%y-%m} to ' if f['start'] else 'up to ')
        parts[-1] += f'{f["end"]:%y-%m}' if f['end'] else 'latest'
    parts.append(f'{f["year"]} vs {f["compare"]}')
    return ', '.join(parts)
