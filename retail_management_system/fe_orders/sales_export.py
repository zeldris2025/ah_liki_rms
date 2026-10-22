"""Daily sales files for FE orders: one CSV row per product line, one file per day.

The day's file (settings.SALES_EXPORT_DIR/sales_YYYY-MM-DD.csv) is rewritten from the
database whenever an order that day is placed or changes status, so it always matches
the system. Days follow this computer's local clock (settings.TIME_ZONE is UTC).
"""
import csv
import logging
import os
import tempfile
from datetime import datetime, time, timedelta

from django.conf import settings

from .models import OrderItem

log = logging.getLogger(__name__)

COLUMNS = ['Date', 'Time', 'Order No', 'Status', 'Shop', 'Territory', 'Address', 'Phone', 'Placed By',
           'Product No', 'Product', 'Category', 'Unit', 'Quantity', 'Unit Price (WST)', 'Line Total (WST)', 'Notes']


def local_day(dt):
    """The local calendar day an aware datetime falls on."""
    return dt.astimezone().date()


def _day_start(day):
    return datetime.combine(day, time.min).astimezone()   # local midnight, as an aware datetime


def items_between(first_day, last_day):
    """Order lines placed from the start of first_day to the end of last_day (local time)."""
    return (OrderItem.objects
            .filter(order__created_at__gte=_day_start(first_day),
                    order__created_at__lt=_day_start(last_day + timedelta(days=1)))
            .select_related('order', 'order__shop', 'order__placed_by', 'product')
            .order_by('order__created_at', 'order_id', 'id'))


def write_csv(out, items):
    w = csv.writer(out)
    w.writerow(COLUMNS)
    for item in items:
        order, product, shop = item.order, item.product, item.order.shop
        placed = order.created_at.astimezone()
        w.writerow([
            placed.strftime('%Y-%m-%d'), placed.strftime('%H:%M'), order.number, order.status,
            shop.name, shop.territory or '', order.address, order.phone,
            order.placed_by.get_full_name() or order.placed_by.username,
            product.product_no, product.name, product.category, product.unit, item.quantity,
            '' if item.unit_price is None else item.unit_price,
            '' if item.line_total is None else item.line_total,
            order.notes,
        ])


def daily_path(day):
    return os.path.join(settings.SALES_EXPORT_DIR, f'sales_{day:%Y-%m-%d}.csv')


def save_daily_file(day):
    """(Re)write the sales file for one day. Written to a temp file first so it's never half-saved."""
    path = daily_path(day)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        # utf-8-sig so Excel shows names like "Fa'atoaga" and "×" correctly
        with os.fdopen(fd, 'w', newline='', encoding='utf-8-sig') as f:
            write_csv(f, items_between(day, day))
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return path


def refresh_for_order(order):
    """Keep the order's daily file current. Never lets a file problem break ordering."""
    try:
        save_daily_file(local_day(order.created_at))
    except OSError:
        log.exception('Could not save the daily sales file for %s', order.number)


# ── Downloads from the FE Orders page ─────────────────────────────────────────

PERIODS = [('today', 'Today'), ('yesterday', 'Yesterday'), ('7days', 'Last 7 days'), ('week', 'This week'),
           ('month', 'This month'), ('last_month', 'Last month'), ('all', 'All orders')]


def period_dates(key, today=None):
    """(first day, last day, label) for a quick period; 'all' starts at the first order ever placed."""
    from .models import Order
    today = today or datetime.now().astimezone().date()
    if key == 'yesterday':
        d = today - timedelta(days=1)
        return d, d, f'{d:%d %b %Y}'
    if key == '7days':
        start = today - timedelta(days=6)                  # today and the 6 days before it
        return start, today, f'{start:%d %b} to {today:%d %b %Y}'
    if key == 'week':
        start = today - timedelta(days=today.weekday())   # Monday
        return start, today, f'week of {start:%d %b %Y}'
    if key == 'month':
        return today.replace(day=1), today, f'{today:%B %Y}'
    if key == 'last_month':
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end, f'{end:%B %Y}'
    if key == 'all':
        first = Order.objects.order_by('created_at').values_list('created_at', flat=True).first()
        return (local_day(first) if first else today), today, 'all orders'
    return today, today, f'{today:%d %b %Y}'


def placed_between(qs, first_day, last_day):
    """Narrow an Order queryset to orders placed from the start of first_day to the end of last_day (local time)."""
    return qs.filter(created_at__gte=_day_start(first_day), created_at__lt=_day_start(last_day + timedelta(days=1)))


def for_export(orders):
    """Oldest first, with everything the files need fetched up front."""
    return orders.select_related('shop', 'placed_by').prefetch_related('items__product').order_by('created_at')


def items_of(orders):
    """The product lines of these orders, in the order they were placed."""
    return (OrderItem.objects.filter(order__in=orders.values('pk'))
            .select_related('order', 'order__shop', 'order__placed_by', 'product')
            .order_by('order__created_at', 'order_id', 'id'))


def daily_totals(orders):
    """[(day, orders, shops, units, total WST)] for each day with orders, oldest first."""
    by_day = {}
    for o in orders:
        d = by_day.setdefault(local_day(o.created_at), {'orders': 0, 'shops': set(), 'units': 0, 'total': 0.0})
        d['orders'] += 1
        d['shops'].add(o.shop_id)
        d['units'] += o.item_count
        d['total'] += float(o.total)
    return [(day, d['orders'], len(d['shops']), d['units'], d['total']) for day, d in sorted(by_day.items())]


def write_daily_csv(out, orders):
    """Daily sales: one row per day, then a TOTAL row."""
    orders = list(for_export(orders))
    w = csv.writer(out)
    w.writerow(['Date', 'Day', 'Orders', 'Shops', 'Units', 'Sales (WST)'])
    for day, n, shops, units, total in daily_totals(orders):
        w.writerow([f'{day:%Y-%m-%d}', f'{day:%A}', n, shops, units, f'{total:.2f}'])
    w.writerow(['TOTAL', '', len(orders), len({o.shop_id for o in orders}), sum(o.item_count for o in orders),
                f'{sum(float(o.total) for o in orders):.2f}'])


def workbook(orders):
    """Excel file with these orders: Orders, Order lines, By shop and By day sheets."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    orders = list(for_export(orders))
    wb = Workbook()
    wb.remove(wb.active)
    head_fill, head_font, money = PatternFill('solid', fgColor='0F172A'), Font(bold=True, color='FFFFFF'), '#,##0.00'

    def sheet(title, headers, rows, widths, money_cols=()):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for cell in ws[1]:
            cell.fill, cell.font, cell.alignment = head_fill, head_font, Alignment(horizontal='center', wrap_text=True)
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
        for col in money_cols:
            for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                row[0].number_format = money
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        return ws

    def when(o):
        return o.created_at.astimezone()

    def who(o):
        return o.placed_by.get_full_name() or o.placed_by.username

    def total(o):
        return float(o.total)

    sheet('Orders', ['Date', 'Time', 'Order No', 'Status', 'Shop', 'Customer Code', 'Territory', 'Placed By',
                     'Products', 'Units', 'Total (WST)', 'Unpriced Lines', 'Notes'],
          ([when(o).strftime('%Y-%m-%d'), when(o).strftime('%H:%M'), o.number, o.status, o.shop.name, o.shop.customer_code or '',
            o.shop.territory or '', who(o), len(o.items.all()), o.item_count, total(o),
            sum(1 for i in o.items.all() if i.unit_price is None) or '', o.notes] for o in orders),
          [12, 8, 12, 11, 34, 14, 10, 16, 10, 8, 14, 10, 40], money_cols=(11,))

    sheet('Order lines', COLUMNS,
          ([when(o).strftime('%Y-%m-%d'), when(o).strftime('%H:%M'), o.number, o.status, o.shop.name, o.shop.territory or '',
            o.address, o.phone, who(o), i.product.product_no, i.product.name, i.product.category, i.product.unit, i.quantity,
            None if i.unit_price is None else float(i.unit_price), None if i.line_total is None else float(i.line_total), o.notes]
           for o in orders for i in o.items.all()),
          [12, 8, 12, 11, 30, 10, 24, 12, 16, 14, 34, 14, 10, 9, 14, 14, 30], money_cols=(15, 16))

    by_shop = {}
    for o in orders:
        s = by_shop.setdefault(o.shop_id, {'shop': o.shop, 'orders': 0, 'units': 0, 'total': 0.0, 'last': when(o)})
        s['orders'] += 1
        s['units'] += o.item_count
        s['total'] += total(o)
        s['last'] = max(s['last'], when(o))
    sheet('By shop', ['Shop', 'Customer Code', 'Territory', 'Orders', 'Units', 'Total (WST)', 'Last Order'],
          ([s['shop'].name, s['shop'].customer_code or '', s['shop'].territory or '', s['orders'], s['units'], s['total'],
            s['last'].strftime('%Y-%m-%d %H:%M')] for s in sorted(by_shop.values(), key=lambda x: -x['total'])),
          [34, 14, 10, 8, 8, 14, 16], money_cols=(6,))

    ws = sheet('By day', ['Date', 'Orders', 'Shops', 'Units', 'Total (WST)'],
               ([f'{day:%Y-%m-%d}', n, shops, units, t] for day, n, shops, units, t in daily_totals(orders)),
               [12, 8, 8, 8, 14], money_cols=(5,))
    ws.append(['TOTAL', len(orders), len(by_shop), sum(o.item_count for o in orders), sum(total(o) for o in orders)])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    ws.cell(row=ws.max_row, column=5).number_format = money

    from io import BytesIO
    out = BytesIO()
    wb.save(out)
    return out.getvalue(), len(orders)
