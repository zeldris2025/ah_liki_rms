import csv
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from shops.models import Shop

from . import office365, sales_export, telegram, whatsapp
from .models import Issue, Order, OrderItem, Product


def _clean(value):
    """Shop fields use 'n/a' as a placeholder; treat it as empty."""
    value = (value or '').strip()
    return '' if value.lower() == 'n/a' else value


# Big shortcut buttons on the Place Order screen. A product belongs to a quick
# link when its quick_link field matches the label, or its category or name
# contains one of the keywords (case and spaces are ignored, so 'tiptop' also
# matches 'Tip Top Vanilla 2L'). Any other quick_link value set on a product
# (e.g. from the CSV upload) gets its own button after these.
QUICK_LINKS = [
    {'label': 'Tip Top', 'icon': '🍦', 'keywords': ['tiptop']},
    {'label': 'Meat',    'icon': '🥩', 'keywords': ['meat']},
    {'label': 'Dairy',   'icon': '🥛', 'keywords': ['dairy']},
]


def _office_only(request):
    if request.is_fe:
        raise Http404


# ══════════════════════════════════════════════════════════════════════════════
# FE SCREENS
# ══════════════════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def fe_home(request):
    orders = Order.objects.all() if not request.is_fe else Order.objects.filter(placed_by=request.user)
    issues = Issue.objects.all() if not request.is_fe else Issue.objects.filter(reported_by=request.user)
    return render(request, 'fe_orders/home.html', {
        'pending_orders': orders.filter(status='Pending').count(),
        'open_issues':    issues.exclude(status='Resolved').count(),
    })


@login_required(login_url='login')
def fe_place_order(request):
    if request.method == 'POST':
        error = _save_order(request)
        if isinstance(error, Order):
            order = error
            detail = reverse('fe_order_detail', args=[order.pk])
            telegram.notify_new_order(order, request.build_absolute_uri(detail))
            whatsapp.notify_new_order(order, request.build_absolute_uri(detail))
            office365.notify_new_order(order, request.build_absolute_uri(detail))
            transaction.on_commit(lambda: sales_export.refresh_for_order(order))
            messages.success(request, f'Order {order.number} placed for {order.shop.name}.')
            return redirect(detail + '?placed=1')
        messages.error(request, error)
        return redirect(request.get_full_path())

    shops = [{'id': s.id, 'name': s.name, 'address': _clean(s.address), 'phone': _clean(s.phone),
              'territory': s.territory or '', 'island': s.island}
             for s in Shop.objects.order_by('name')]
    products = [{'id': p.id, 'name': p.name, 'category': p.category, 'unit': p.unit,
                 'price': float(p.unit_price) if p.unit_price is not None else None,
                 'available': p.available, 'quick_link': p.quick_link}
                for p in Product.objects.all()]
    return render(request, 'fe_orders/place_order.html', {
        'order_data': {
            'shops':      shops,
            'products':   products,
            'quick_links': QUICK_LINKS,
            'preselect':  request.GET.get('shop'),
        },
    })


def _save_order(request):
    """Create the order from the POSTed form. Returns the Order, or an error message."""
    shop = Shop.objects.filter(pk=request.POST.get('shop_id') or 0).first()
    if not shop:
        return 'Choose a shop before placing the order.'
    try:
        lines = json.loads(request.POST.get('items') or '[]')
        wanted = {int(l['product']): int(l['qty']) for l in lines if int(l['qty']) > 0}
    except (ValueError, TypeError, KeyError):
        return 'The product list could not be read. Please try again.'
    if not wanted:
        return 'Add at least one product.'
    if any(q > 9999 for q in wanted.values()):
        return 'Quantities must be under 10,000.'

    products = Product.objects.in_bulk(wanted.keys())
    unavailable = [p.name for p in products.values() if not p.available]
    if len(products) != len(wanted):
        return 'One of the products no longer exists. Please reload the page.'
    if unavailable:
        return 'Out of stock: ' + ', '.join(unavailable) + '. Remove it and try again.'

    with transaction.atomic():
        order = Order.objects.create(
            shop=shop, placed_by=request.user,
            address=request.POST.get('address', '').strip()[:255],
            phone=request.POST.get('phone', '').strip()[:30],
            notes=request.POST.get('notes', '').strip(),
        )
        OrderItem.objects.bulk_create([
            OrderItem(order=order, product=products[pid], quantity=qty, unit_price=products[pid].unit_price)
            for pid, qty in wanted.items()
        ])
    return order


def _visible_orders(request):
    qs = Order.objects.select_related('shop', 'placed_by').prefetch_related('items')
    return qs.filter(placed_by=request.user) if request.is_fe else qs


def _filter_orders(request, qs):
    """Apply the order list's filters: ?period= (or ?from=&to=), ?status= and ?q=.
    Returns the narrowed queryset and the filters, so the list and its downloads always match."""
    get = request.GET
    period, first, last = get.get('period', ''), None, None
    if period in dict(sales_export.PERIODS):
        if period != 'all':
            first, last, _ = sales_export.period_dates(period)
    elif get.get('from') or get.get('to'):
        try:
            first = date.fromisoformat(get.get('from') or get['to'])
            last = date.fromisoformat(get.get('to') or get['from'])
        except ValueError:
            first = last = None
        else:
            period = 'custom'
            if last < first:
                first, last = last, first
    if period not in dict(sales_export.PERIODS) and period != 'custom':
        period = 'all'
    if first:
        qs = sales_export.placed_between(qs, first, last)
    status = get.get('status', '')
    q = get.get('q', '').strip()
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(shop__name__icontains=q) | Q(notes__icontains=q))
    return qs, {'period': period, 'first': first, 'last': last, 'status': status, 'q': q}


def _filter_query(f, **changes):
    """The list's query string with some filters changed, e.g. _filter_query(f, status='Pending')."""
    f = {**f, **changes}
    params = {'status': f['status'], 'q': f['q']}
    if f['period'] == 'custom':
        params.update({'from': f'{f["first"]:%Y-%m-%d}', 'to': f'{f["last"]:%Y-%m-%d}'})
    elif f['period'] != 'all':
        params['period'] = f['period']
    return urlencode({k: v for k, v in params.items() if v})


@login_required(login_url='login')
def fe_order_list(request):
    qs, f = _filter_orders(request, _visible_orders(request))
    sums = (OrderItem.objects.filter(order__in=qs.exclude(status='Cancelled').values('pk'))
            .aggregate(units=Sum('quantity'),
                       sales=Sum(ExpressionWrapper(F('quantity') * F('unit_price'),
                                                   output_field=DecimalField(max_digits=14, decimal_places=2)))))
    if f['period'] == 'custom':
        period_label = f'{f["first"]:%d %b %Y}' + ('' if f['first'] == f['last'] else f' – {f["last"]:%d %b %Y}')
    else:
        period_label = dict(sales_export.PERIODS)[f['period']]
    return render(request, 'fe_orders/order_list.html', {
        'orders': qs[:200], 'order_count': qs.count(), 'cancelled_count': qs.filter(status='Cancelled').count(),
        'units': sums['units'] or 0, 'sales': sums['sales'] or 0,
        'status': f['status'], 'q': f['q'], 'period': f['period'], 'period_label': period_label,
        'from_day': f['first'], 'to_day': f['last'],
        'pick_from': f['first'] or date.today(), 'pick_to': f['last'] or date.today(), 'statuses': Order.STATUS_CHOICES,
        'status_links': [('', 'All', _filter_query(f, status=''))]
                        + [(v, label, _filter_query(f, status=v)) for v, label in Order.STATUS_CHOICES],
        'period_links': [(k, label, _filter_query(f, period=k)) for k, label in sales_export.PERIODS],
        'query': _filter_query(f),
        'today': date.today(), 'export_dir': settings.SALES_EXPORT_DIR,
    })


@login_required(login_url='login')
def sales_export_download(request):
    """Office only: download the orders the list is showing (same ?period= / ?from=&to=, ?status=, ?q=) as
    an Excel workbook (orders, lines, by shop, by day), a CSV of product lines (?format=csv),
    or a daily sales CSV with one row per day (?format=daily)."""
    _office_only(request)
    orders, f = _filter_orders(request, Order.objects.all())
    if request.GET.get('skip_cancelled') == '1':
        orders = orders.exclude(status='Cancelled')
    if f['first']:
        name = f'fe_orders_{f["first"]:%Y-%m-%d}' + ('' if f['first'] == f['last'] else f'_to_{f["last"]:%Y-%m-%d}')
    else:
        name = 'fe_orders_all'
    fmt = request.GET.get('format')

    if fmt in ('csv', 'daily'):
        if fmt == 'daily':
            name = name.replace('fe_orders_', 'fe_daily_sales_')
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{name}.csv"'
        response.write('﻿')   # BOM so Excel reads the file as UTF-8
        if fmt == 'daily':
            sales_export.write_daily_csv(response, orders)
        else:
            sales_export.write_csv(response, sales_export.items_of(orders))
        return response

    content, _ = sales_export.workbook(orders)
    response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{name}.xlsx"'
    return response


@login_required(login_url='login')
def fe_order_detail(request, order_id):
    order = get_object_or_404(_visible_orders(request), pk=order_id)
    if request.method == 'POST':
        _office_only(request)
        if 'resend_email' in request.POST:
            if office365.is_configured('order'):
                office365.notify_new_order(order, request.build_absolute_uri(request.path))
                messages.success(request, f'{order.number} is being emailed again.')
            else:
                messages.error(request, 'Email isn’t set up yet: add the Microsoft 365 details and recipients to the .env file.')
            return redirect('fe_order_detail', order_id=order.pk)
        if 'resend_telegram' in request.POST:
            if telegram.is_configured():
                telegram.notify_new_order(order, request.build_absolute_uri(request.path))
                messages.success(request, f'{order.number} is being sent to the Telegram group again.')
            else:
                messages.error(request, 'Telegram isn’t set up yet: add the bot token and chat ID to the .env file.')
            return redirect('fe_order_detail', order_id=order.pk)
        if 'resend_whatsapp' in request.POST:
            if whatsapp.is_configured():
                whatsapp.notify_new_order(order, request.build_absolute_uri(request.path))
                messages.success(request, f'{order.number} is being sent to the WhatsApp group again.')
            else:
                messages.error(request, 'WhatsApp isn’t set up yet: add the WAHA address and group chat ID to the .env file.')
            return redirect('fe_order_detail', order_id=order.pk)
        new = request.POST.get('status')
        if new in dict(Order.STATUS_CHOICES):
            order.status = new
            order.save(update_fields=['status', 'updated_at'])
            transaction.on_commit(lambda: sales_export.refresh_for_order(order))
            messages.success(request, f'{order.number} marked {new}.')
        return redirect('fe_order_detail', order_id=order.pk)
    return render(request, 'fe_orders/order_detail.html', {
        'order': order, 'items': order.items.select_related('product'), 'statuses': Order.STATUS_CHOICES,
    })


@login_required(login_url='login')
def fe_issue_list(request):
    qs = Issue.objects.select_related('shop', 'reported_by')
    if request.is_fe:
        qs = qs.filter(reported_by=request.user)
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'fe_orders/issue_list.html', {
        'issues': qs[:200], 'status': status, 'statuses': Issue.STATUS_CHOICES,
    })


@login_required(login_url='login')
def fe_report_issue(request):
    if request.method == 'POST':
        category = request.POST.get('category', '')
        description = request.POST.get('description', '').strip()
        if category not in dict(Issue.CATEGORY_CHOICES) or not description:
            messages.error(request, 'Pick an issue type and describe the problem.')
        else:
            issue = Issue.objects.create(
                shop=Shop.objects.filter(pk=request.POST.get('shop_id') or 0).first(),
                category=category, description=description,
                photo=request.FILES.get('photo') or '',
                reported_by=request.user,
            )
            office365.notify_new_issue(issue, request.build_absolute_uri(reverse('fe_issue_list')))
            messages.success(request, 'Issue reported. The office has been notified.')
            return redirect('fe_issue_list')
    shops = [{'id': s.id, 'name': s.name, 'address': _clean(s.address), 'territory': s.territory or ''}
             for s in Shop.objects.order_by('name')]
    return render(request, 'fe_orders/report_issue.html', {
        'categories': Issue.CATEGORY_CHOICES, 'shops': shops,
        'preselect': request.GET.get('shop'),
    })


@login_required(login_url='login')
@require_POST
def fe_issue_status(request, issue_id):
    _office_only(request)
    issue = get_object_or_404(Issue, pk=issue_id)
    new = request.POST.get('status')
    if new in dict(Issue.STATUS_CHOICES):
        issue.status = new
        issue.save(update_fields=['status', 'updated_at'])
    return redirect(request.POST.get('next') or 'fe_issue_list')


# ══════════════════════════════════════════════════════════════════════════════
# OFFICE: PRODUCT CATALOGUE
# ══════════════════════════════════════════════════════════════════════════════

# (model field, CSV header). The upload also accepts the old lowercase names and
# common variants from other systems; see HEADER_ALIASES.
PRODUCT_COLUMNS = [
    ('product_no',          'Product No'),
    ('name',                'Product Name'),
    ('category',            'Product Category'),
    ('unit',                'Unit of Measure Code'),
    ('cost',                'Cost'),
    ('unit_price',          'Unit Price'),
    ('unit_price_incl_vat', 'Unit Price Including VAT'),
    ('available',           'Available'),
    ('quick_link',          'Quick Link'),
]
MONEY_FIELDS = ('cost', 'unit_price', 'unit_price_incl_vat')
NO_QUICK_LINK = ('NONE', '-')   # CSV values that remove a product's quick link


def _header_key(header):
    """'Unit Price Incl. VAT' -> 'unitpriceinclvat'"""
    return re.sub(r'[^a-z0-9]', '', (header or '').lower())


HEADER_ALIASES = {
    'product_no':          ['no', 'productnumber', 'productcode', 'itemno', 'itemnumber', 'code', 'sku'],
    'name':                ['name', 'description', 'itemname'],
    'category':            ['category', 'itemcategory', 'itemcategorycode', 'productcategorycode'],
    'unit':                ['unit', 'uom', 'uomcode', 'unitofmeasure', 'baseunitofmeasure'],
    'cost':                ['unitcost', 'costprice'],
    'unit_price':          ['price'],
    'unit_price_incl_vat': ['unitpriceinclvat', 'unitpriceincvat', 'priceinclvat', 'priceincludingvat'],
    'available':           ['availability', 'instock'],
    'quick_link':          [],
}
HEADER_TO_FIELD = {}
for _field, _header in PRODUCT_COLUMNS:
    for _alias in [_header, _field] + HEADER_ALIASES[_field]:
        HEADER_TO_FIELD[_header_key(_alias)] = _field


def _money(value):
    """'$1,234.50' / 'WST 12' -> Decimal, blank -> None. Raises InvalidOperation if not a positive number."""
    value = re.sub(r'(?i)wst|\$|,|\s', '', str(value or ''))
    if not value:
        return None
    amount = Decimal(value)
    if amount < 0 or not amount.is_finite():
        raise InvalidOperation
    return amount


def _product_row(p):
    return [p.product_no, p.name, p.category, p.unit,
            *('' if getattr(p, f) is None else getattr(p, f) for f in MONEY_FIELDS),
            'TRUE' if p.available else 'FALSE', p.quick_link]


@login_required(login_url='login')
def product_list(request):
    qs = Product.objects.annotate(times_ordered=Count('order_items'))
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    availability = request.GET.get('availability', '')
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(category__icontains=q) | Q(product_no__iexact=q))
    if category:
        qs = qs.filter(category=category)
    if availability in ('1', '0'):
        qs = qs.filter(available=availability == '1')
    return render(request, 'fe_orders/product_list.html', {
        'products': qs, 'q': q, 'category': category, 'availability': availability,
        'categories': Product.objects.values_list('category', flat=True).distinct().order_by('category'),
        'total': Product.objects.count(),
        'out_of_stock': Product.objects.filter(available=False).count(),
    })


def _product_from_post(post, product=None):
    """Validate the add/edit form. Returns (product, errors)."""
    product = product or Product()
    errors = []
    product.product_no = post.get('product_no', '').strip()[:50]
    product.name = post.get('name', '').strip()
    product.category = post.get('category', '').strip()
    product.unit = post.get('unit', '').strip()
    product.available = post.get('available') == 'on'
    product.quick_link = post.get('quick_link', '').strip()[:50]
    labels = {'cost': 'Cost', 'unit_price': 'Unit price', 'unit_price_incl_vat': 'Unit price incl. VAT'}
    for field in MONEY_FIELDS:
        try:
            setattr(product, field, _money(post.get(field)))
        except InvalidOperation:
            errors.append(f'{labels[field]} must be a positive number, e.g. 45.50')
    if not product.name:
        errors.append('Product name is required.')
    if not product.category:
        errors.append('Category is required.')
    dup = Product.objects.filter(name__iexact=product.name).exclude(pk=product.pk)
    if product.name and dup.exists():
        errors.append(f'A product called "{product.name}" already exists.')
    if product.product_no and Product.objects.filter(product_no=product.product_no).exclude(pk=product.pk).exists():
        errors.append(f'Product No {product.product_no} is already used by another product.')
    return product, errors


@login_required(login_url='login')
def product_form(request, product_id=None):
    product = get_object_or_404(Product, pk=product_id) if product_id else None
    errors = []
    if request.method == 'POST':
        product, errors = _product_from_post(request.POST, product)
        if not errors:
            product.save()
            messages.success(request, f'Saved {product.name}.')
            return redirect('product_list')
    return render(request, 'fe_orders/product_form.html', {
        'product': product, 'errors': errors,
        'categories': Product.objects.values_list('category', flat=True).distinct().order_by('category'),
        'quick_links': _quick_link_names(),
    })


def _quick_link_names():
    """Quick link labels for the form's suggestions: the built-in ones, then any others in use."""
    names = [q['label'] for q in QUICK_LINKS]
    seen = {n.lower() for n in names}
    for n in Product.objects.exclude(quick_link='').values_list('quick_link', flat=True).distinct().order_by('quick_link'):
        if n.lower() not in seen:
            seen.add(n.lower())
            names.append(n)
    return names


@login_required(login_url='login')
@require_POST
def product_toggle(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    product.available = not product.available
    product.save(update_fields=['available'])
    return redirect(request.POST.get('next') or 'product_list')


@login_required(login_url='login')
@require_POST
def product_delete(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if product.order_items.exists():
        messages.error(request, f'{product.name} is on existing orders, so it can’t be deleted. '
                                'Mark it out of stock instead.')
    else:
        product.delete()
        messages.success(request, f'Deleted {product.name}.')
    return redirect('product_list')


def _truthy(value, default):
    value = str(value or '').strip().upper()
    if not value:
        return default
    return value in ('TRUE', 'YES', 'Y', '1', 'AVAILABLE', 'IN STOCK')


@login_required(login_url='login')
def product_import(request):
    """Upload a product CSV. Rows match an existing product by Product No, then by name.
    New products are created; existing ones are updated where the CSV has a value."""
    result = None
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            text = request.FILES['csv_file'].read().decode('utf-8-sig')
        except UnicodeDecodeError:
            messages.error(request, 'The file must be a CSV saved as UTF-8 (in Excel: Save As → CSV UTF-8).')
            return redirect('product_import')
        reader = csv.reader(StringIO(text))
        headers = [HEADER_TO_FIELD.get(_header_key(h)) for h in next(reader, [])]
        if 'name' not in headers and 'product_no' not in headers:
            messages.error(request, 'The CSV needs a "Product No" or "Product Name" column. '
                                    'Download the template to see the format.')
            return redirect('product_import')

        tracked = [f for f, _ in PRODUCT_COLUMNS]
        result = {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': []}
        with transaction.atomic():
            for row_num, cells in enumerate(reader, start=2):
                row = {f: (v or '').strip() for f, v in zip(headers, cells) if f}
                number, name = row.get('product_no', ''), row.get('name', '')
                if not number and not name:
                    continue
                label = f'Row {row_num} ({name or number})'

                product = Product.objects.filter(product_no=number).first() if number else None
                if product is None and name:
                    product = Product.objects.filter(name__iexact=name).first()
                    if product and number and product.product_no and product.product_no != number:
                        result['errors'].append(f'{label}: that name already belongs to Product No {product.product_no}')
                        continue
                is_new = product is None
                if is_new:
                    if not name:
                        result['errors'].append(f'{label}: Product Name is required for new products')
                        continue
                    product = Product(available=True)
                before = [getattr(product, f) for f in tracked]

                if name and name != product.name:
                    if Product.objects.filter(name__iexact=name).exclude(pk=product.pk).exists():
                        result['errors'].append(f'{label}: another product is already called "{name}"')
                        continue
                    product.name = name
                if number:
                    product.product_no = number[:50]
                for field in ('category', 'unit'):
                    if row.get(field):
                        setattr(product, field, row[field])
                try:
                    for field in MONEY_FIELDS:
                        if row.get(field):
                            setattr(product, field, _money(row[field]))
                except InvalidOperation:
                    header = dict(PRODUCT_COLUMNS)[field]
                    result['errors'].append(f'{label}: {header} "{row[field]}" is not a number')
                    continue
                if 'available' in row:
                    product.available = _truthy(row['available'], product.available)
                if row.get('quick_link'):
                    product.quick_link = '' if row['quick_link'].upper() in NO_QUICK_LINK else row['quick_link'][:50]

                if not product.category:
                    result['errors'].append(f'{label}: Product Category is required for new products')
                    continue
                if is_new:
                    product.save()
                    result['created'] += 1
                elif before != [getattr(product, f) for f in tracked]:
                    product.save()
                    result['updated'] += 1
                else:
                    result['unchanged'] += 1
    return render(request, 'fe_orders/product_import.html', {'result': result})


@login_required(login_url='login')
def product_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products_template.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in PRODUCT_COLUMNS])
    w.writerow(['10001', 'Example Soda Can 330ml', 'Soda', 'CTN', '22.00', '28.50', '32.78', 'TRUE', ''])
    w.writerow(['10002', 'Example Tip Top Vanilla 2L', 'Ice Cream', 'EA', '14.00', '18.00', '20.70', 'TRUE', 'Tip Top'])
    return response


@login_required(login_url='login')
def product_export(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in PRODUCT_COLUMNS])
    for p in Product.objects.all():
        w.writerow(_product_row(p))
    return response
