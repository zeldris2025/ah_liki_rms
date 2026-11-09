"""Product QTY Sales: quantity sold per product, this year against last year.

The QTY dashboard (what the Product QTY Sales group see at /), the analytics, Product QTY and the CSV upload. Every page takes the
same filters (see report.read_filters) and its CSV export has exactly what's on screen.
Who may open these is decided in shops.access (the Product QTY Sales group and Managers)."""
import csv
import re
from datetime import date
from decimal import InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from shops.client_import import parse_money

from . import csv_import, quick_links, report
from .models import QtyPinnedProduct, QtyProductGroup, QtySales, QtyTarget

VIEWS = [('products', 'By product'), ('rows', 'Month by month')]


def _keep(request, *drop):
    """The page's query string without some keys, for links that change one filter."""
    return urlencode([(k, v) for k, vs in request.GET.lists() if k not in drop + ('export', 'page') for v in vs])


def _context(request, f):
    return {'f': f, 'period_label': report.period_label(f), 'months': list(enumerate(report.MONTHS, start=1)),
            'query': _keep(request), 'has_data': QtySales.objects.exists()}


def _csv(filename, header, rows):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')
    w = csv.writer(response)
    w.writerow(header)
    w.writerows(rows)
    return response


def _pct(c):
    return '' if c['pct'] is None else f'{c["pct"]:+.1f}%'


def _products_csv(f, rows):
    return _csv(f'product_qty_sales_{f["year"]}_vs_{f["compare"]}_{f["period"]}.csv',
                ['Product Code', 'Product Name', f'QTY {f["compare"]}', f'QTY {f["year"]}', 'Change', 'Change %',
                 f'Share of {f["year"]} %'],
                [[r['code'], r['name'], r['last'], r['this'], r['change']['n'], _pct(r['change']), r['share']]
                 for r in rows])


@login_required(login_url='login')
def dashboard(request):
    """What the Product QTY Sales group see at /: this year to date against the same months last year, with the movers."""
    f = report.read_filters({})
    qs = QtySales.objects.all()
    rows = report.compare_rows(qs, f)
    latest = qs.filter(month__year=f['year']).order_by('-month').values_list('month', flat=True).first()
    month = None
    if latest:
        this, last = (report.total(qs.filter(month__year=y, month__month=latest.month)) for y in (f['year'], f['compare']))
        month = {'date': latest, 'this': this, 'last': last, 'change': report.change(this, last)}
    gainers = sorted((r for r in rows if r['change']['n'] > 0), key=lambda r: -r['change']['n'])[:5]
    losers = sorted((r for r in rows if r['change']['n'] < 0), key=lambda r: r['change']['n'])[:5]
    return render(request, 'aj_sales/dashboard.html', {
        **_context(request, f), 'summary': report.summary(qs, f, rows), 'month': month,
        'top': rows[:8], 'gainers': gainers, 'losers': losers,
        'chart': report.chart_data(qs, f, rows),
    })


@login_required(login_url='login')
def analytics(request):
    """Charts comparing the two years: month by month, running total, top products and the biggest movers.
    ?export=monthly|products downloads that table as CSV."""
    f = report.read_filters(request.GET)
    qs = report.scope(f)
    rows = report.compare_rows(qs, f)
    chart = report.chart_data(qs, f, rows)

    export = request.GET.get('export')
    if export == 'products':
        return _products_csv(f, rows)
    if export == 'monthly':
        this, last = report.monthly(qs, f['year']), report.monthly(qs, f['compare'])
        lines = []
        for i, name in enumerate(report.MONTHS):
            c = report.change(this[i] or 0, last[i] or 0)
            lines.append([name, last[i] or 0, this[i] or 0, c['n'], _pct(c)])
        return _csv(f'product_qty_sales_monthly_{f["year"]}_vs_{f["compare"]}.csv',
                    ['Month', f'QTY {f["compare"]}', f'QTY {f["year"]}', 'Change', 'Change %'], lines)

    monthly = []
    for i, name in enumerate(report.MONTHS):
        this, last = chart['monthly']['this'][i], chart['monthly']['last'][i]
        monthly.append({'name': name, 'this': this, 'last': last, 'picked': i + 1 in f['months'],
                        'change': report.change(this or 0, last or 0) if this is not None or last is not None else None})
    names = report.product_names()
    return render(request, 'aj_sales/analytics.html', {
        **_context(request, f), 'summary': report.summary(qs, f, rows), 'chart': chart, 'monthly': monthly,
        'product_options': sorted(names.items(), key=lambda p: p[1].lower()),
        'product_name': names.get(f['product'].upper(), f['product']),
        'keep_no_product': _keep(request, 'product'),
        'quick': quick_links.panel(f, request.GET.get('lm', '')),
        'page_url': request.get_full_path(), 'keep_links': _keep(request, 'group', 'product'),
    })


@login_required(login_url='login')
def product_qty(request):
    """Product QTY: every product with this year's QTY next to last year's, and on the right the product pairs
    on the right are the quick links. ?view=products|rows, ?sort=this|last|change|drop|pct|name, ?export=1 downloads the table."""
    f = report.read_filters(request.GET)
    qs = report.scope(f)
    view = request.GET.get('view') if request.GET.get('view') in dict(VIEWS) else 'products'
    sort = request.GET.get('sort') if request.GET.get('sort') in report.SORTS else 'this'
    table = report.compare_rows(qs, f)

    if view == 'rows':
        rows = report.in_period(qs, f, f['year']).order_by('-month', '-qty')
        if request.GET.get('export'):
            return _csv(f'product_qty_sales_months_{f["year"]}_{f["period"]}.csv', [h for _, h in csv_import.COLUMNS],
                        [[r.product_code, r.product_name, f'{r.month:%Y-%m}', r.qty] for r in rows])
    else:
        rows = sorted(table, key=report.SORTS[sort])
        if request.GET.get('export'):
            return _products_csv(f, rows)

    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    return render(request, 'aj_sales/product_qty.html', {
        **_context(request, f), 'summary': report.summary(qs, f, table),
        'views': VIEWS, 'view': view, 'sort': sort, 'page_obj': page,
        'biggest': float(max([max(r['this'], r['last']) for r in table] or [0])) or 1,
        'trend': report.trend(qs, f), 'quick': quick_links.panel(f, request.GET.get('lm', '')),
        'page_url': request.get_full_path(), 'keep_links': _keep(request, 'group', 'product'),
        'keep_no_sort': _keep(request, 'sort'), 'keep_no_view': _keep(request, 'view', 'sort'),
    })


@login_required(login_url='login')
def import_csv(request):
    """Upload Product QTY from a CSV. Matches on Product Code + Month; see csv_import.py for the rules."""
    from shops.client_import import ImportFileError
    extra = {'columns': csv_import.COLUMNS}
    result = None
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            result = csv_import.import_qty_sales(request.FILES['csv_file'])
        except ImportFileError as exc:
            return render(request, 'aj_sales/import.html', {**extra, 'error': str(exc)})
    return render(request, 'aj_sales/import.html', {**extra, 'result': result})


@login_required(login_url='login')
def download_template(request):
    """The Product QTY CSV template."""
    return _csv('product_qty_sales_template.csv', [h for _, h in csv_import.COLUMNS], [
        ['P1001', 'Example Product 500g', '2026-09', '1200'],
        ['P1002', 'Example Product 1kg', '2026-09', '480'],
        ['P1001', 'Example Product 500g', '2025-09', '1050'],
    ])


# ── Quick links: pins, groups and targets (like Product Sales, in units) ──

@login_required(login_url='login')
@require_POST
def pin(request):
    """Pin or unpin a product in the quick links."""
    code = request.POST.get('code', '').strip().upper()
    if code:
        pinned = QtyPinnedProduct.objects.filter(product_code=code).first()
        if pinned:
            pinned.delete()
        elif QtySales.objects.filter(product_code=code).exists():
            QtyPinnedProduct.objects.create(product_code=code)
    nxt = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        nxt = reverse('aj_product_qty')   # only ever go back to a page on this site
    return redirect(nxt)


@login_required(login_url='login')
def group_form(request, group_id=None):
    """Add or edit a product group: products picked by hand, matched by keyword, or both."""
    group = get_object_or_404(QtyProductGroup, pk=group_id) if group_id else QtyProductGroup(
        name=request.GET.get('name', '').strip()[:100], keywords=request.GET.get('keywords', '').strip()[:255])
    errors = []
    if request.method == 'POST':
        if group.pk and 'delete' in request.POST:
            group.delete()
            return redirect('aj_product_qty')
        group.name = request.POST.get('name', '').strip()[:100]
        group.keywords = ', '.join(k.strip() for k in request.POST.get('keywords', '').split(',') if k.strip())[:255]

        def codes(field):   # unique codes, in the order given
            return list(dict.fromkeys(c.upper() for c in re.split(r'[\s,;]+', request.POST.get(field, '')) if c))
        group.product_codes = '\n'.join(codes('product_codes'))
        group.exclude_codes = '\n'.join(codes('exclude_codes'))
        if not group.name:
            errors.append('Give the group a name, e.g. Tip Top.')
        elif QtyProductGroup.objects.filter(name__iexact=group.name).exclude(pk=group.pk).exists():
            errors.append(f'There’s already a group called “{group.name}”.')
        if not group.keyword_list() and not group.code_list():
            errors.append('Add at least one keyword or product code.')
        if not errors:
            group.save()
            return redirect(f"{reverse('aj_product_qty')}?group={group.pk}")
    # every product, for the picker (searching and ticking happen in the browser)
    catalogue = [[r['product_code'], r['name'] or r['product_code'], float(r['total'])] for r in
                 QtySales.objects.values('product_code').annotate(name=Max('product_name'), total=Sum('qty'))
                 .order_by('-total')]
    return render(request, 'aj_sales/group_form.html', {
        'group': group, 'errors': errors, 'catalogue': catalogue,
        'picked': group.code_list(), 'excluded': group.exclude_list(),
    })


@login_required(login_url='login')
def targets(request):
    """Set monthly QTY targets by hand for groups and pinned products. A blank box uses the same month last year."""
    year = report.read_filters(request.GET)['year']
    errors = []
    if request.method == 'POST':
        with transaction.atomic():
            for row in quick_links.target_grid(year):
                who = {'group': row['key']} if row['kind'] == 'group' else {'product_code': row['key']}
                for i, cell in enumerate(row['cells']):
                    month = date(year, i + 1, 1)
                    raw = request.POST.get(cell['name'], '').strip()
                    if not raw:
                        QtyTarget.objects.filter(month=month, **who).delete()
                        continue
                    try:
                        qty = parse_money(raw)
                    except (InvalidOperation, ValueError):
                        errors.append(f"{row['label']}, {cell['label']}: “{raw}” is not a number")
                        continue
                    QtyTarget.objects.update_or_create(month=month, **who, defaults={'qty': qty})
            if errors:
                transaction.set_rollback(True)
        if not errors:
            messages.success(request, f'QTY targets for {year} saved.')
            return redirect(f"{reverse('aj_product_qty')}?year={year}")
    rows = quick_links.target_grid(year)
    if errors:   # show what was typed so it can be fixed
        for row in rows:
            for cell in row['cells']:
                cell['value'] = request.POST.get(cell['name'], '')
    return render(request, 'aj_sales/targets.html', {
        'rows': rows, 'year': year, 'errors': errors, 'months': report.MONTHS, 'years': report.years(),
    })
