"""CSV upload for Product QTY Sales: one row per product per month (the Monthly Sales upload, in units, by product).

Safe to upload the same file again: a row matches the quantity already saved for its Product Code + Month and
replaces it, so a month is never counted twice. Rows for the same product and month in one file (e.g. one per
invoice or client) are added together. The name is only for reading; the code decides the product, and the latest
name is kept.
"""
from decimal import InvalidOperation

from django.db import transaction

from shops.client_import import ImportFileError, finish, log, new_result, parse_money, read_rows, skip
from shops.product_sales import parse_yy_mm

from .models import QtySales

# (field, CSV header) in the order the template uses
COLUMNS = [
    ('product_code', 'Product Code'),
    ('product_name', 'Product Name'),
    ('month',        'Month'),
    ('qty',          'QTY'),
]
ALIASES = {
    'product_code': ['productno', 'productnumber', 'itemno', 'itemcode', 'sku', 'code'],
    'product_name': ['product', 'description', 'itemname', 'item', 'name'],
    'month':        ['date', 'period', 'salesmonth', 'dateyymm', 'yymm'],
    'qty':          ['quantity', 'qtysold', 'quantitysold', 'units', 'unitssold', 'totalqty', 'cases'],
}


def number(value):
    """1234.5 → '1,234.5'; whole numbers without decimals."""
    return f'{value:,.2f}'.rstrip('0').rstrip('.')


def import_qty_sales(uploaded):
    present, rows = read_rows(uploaded, COLUMNS, ALIASES)
    missing = [h for f, h in COLUMNS if f != 'product_name' and f not in present]
    if missing:
        raise ImportFileError(f'The file needs these columns: {", ".join(missing)}. Download the template to see the format.')

    result = new_result(combined=0)
    totals, lines, names = {}, {}, {}   # (product, month) → total QTY, file rows, latest name
    for number_, row in rows:
        code = row.get('product_code', '').upper()
        name = ' '.join(row.get('product_name', '').split())[:255]
        item = ' · '.join(v for v in (code, name) if v)
        if not code:
            skip(result, number_, item, 'Product Code is missing.')
            continue
        try:
            month = parse_yy_mm(row.get('month', ''))
        except ValueError:
            skip(result, number_, item, f'"{row.get("month", "")}" is not a month. Use e.g. 2026-09, 26-09 or Sep-26.')
            continue
        try:
            qty = parse_money(row.get('qty', ''))
        except (InvalidOperation, ValueError):
            skip(result, number_, item, f'QTY "{row.get("qty", "")}" is not a number.')
            continue
        key = (code, month)
        if key in totals:
            result['combined'] += 1
        totals[key] = totals.get(key, 0) + qty
        lines.setdefault(key, []).append(number_)
        names[key] = name or names.get(key, '')

    with transaction.atomic():
        existing = {(r.product_code.upper(), r.month): r
                    for r in QtySales.objects.filter(month__in={k[1] for k in totals})}
        for key, qty in totals.items():
            code, month = key
            name, numbers = names[key], lines[key]
            item = ' · '.join(v for v in (code, name, f'{month:%b %Y}') if v)
            combined = f' (rows {", ".join(map(str, numbers))} added together)' if len(numbers) > 1 else ''
            record = existing.get(key)
            if record is None:
                QtySales.objects.create(product_code=code, product_name=name, month=month, qty=qty)
                result['created'] += 1
                log(result, 'added', numbers, item, f'QTY {number(qty)}{combined}')
                continue
            changes = [f'QTY {number(record.qty)} → {number(qty)}'] if record.qty != qty else []
            if name and record.product_name != name:
                changes.append(f'Name: {record.product_name or "blank"} → {name}')
                record.product_name = name
            if changes:
                record.qty = qty
                record.save()
                result['updated'] += 1
                log(result, 'updated', numbers, item, '; '.join(changes) + combined)
            else:
                result['unchanged'] += 1
                log(result, 'unchanged', numbers, item, f'QTY {number(qty)}{combined}')
    return finish(result)
