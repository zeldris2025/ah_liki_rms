"""CSV uploads for clients and their monthly sales.

Both uploads are safe to repeat every day with the same file:
  * Clients match on Customer Code, which every row needs. A known code updates that client,
    including its name, so renamed shops are renamed here too. Clients that don't have a code yet
    (added before codes existed) are matched by name once and given their code.
  * Monthly sales match on Customer Code + Month; the file's figure replaces the stored total,
    so uploading the same month again never adds it twice. The Customer Name column is only for
    people reading the file; the code decides which client the sales belong to.
Blank cells and missing columns never wipe existing values.
"""
import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO

from django.db import transaction

from .models import MonthlySales, Shop

# (field, CSV header) in the order the template uses
CLIENT_COLUMNS = [
    ('customer_code',  'Customer Code'),
    ('name',           'Name'),
    ('customer_type',  'Customer Type'),
    ('contact_person', 'Contact Person'),
    ('address',        'Address'),
    ('island',         'Island'),
    ('phone',          'Phone Number'),
    ('territory',      'Territory Code'),
    ('email',          'Email'),
]
SALES_COLUMNS = [
    ('customer_code', 'Customer Code'),
    ('customer_name', 'Customer Name'),
    ('month',         'Month'),
    ('sales',         'Sales'),
]

# Other spellings accepted in the header row (compared without case, spaces or punctuation)
ALIASES = {
    'customer_code':  ['code', 'customerno', 'customernumber', 'accountcode', 'accountno', 'no', 'clientcode'],
    'name':           ['customername', 'clientname', 'shopname'],
    'customer_type':  ['type', 'clienttype'],
    'contact_person': ['contact', 'contactname', 'owner'],
    'phone':          ['phone', 'phoneno', 'telephone', 'mobile'],
    'territory':      ['territory', 'territorycode', 'salesterritory'],
    'email':          ['emailaddress', 'email'],
    'customer_name':  ['name', 'clientname', 'shopname'],
    'month':          ['period', 'salesmonth', 'date'],
    'sales':          ['totalsales', 'amount', 'salesamount', 'total', 'salestotal'],
    # older client columns, still accepted if present
    'tip_top':        ['tiptop'],
    'taula_fridge':   ['taulafridge'],
    'talofa_voucher': ['talofavoucher'],
    'faakau_com':     ['faakaucom', 'faakau'],
}
FLAG_FIELDS = ('tip_top', 'taula_fridge', 'talofa_voucher', 'faakau_com')
ISLANDS = {'upolu': 'Upolu', 'savaii': 'Savaii', "savai'i": 'Savaii', 'savai‘i': 'Savaii'}


class ImportFileError(Exception):
    """The file as a whole can't be read (wrong encoding, missing key columns)."""


def _key(text):
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())


def read_rows(uploaded, columns, aliases=None):
    """Decode the file and return (headers present, rows as {field: text}) with the first data row numbered 2."""
    aliases = ALIASES if aliases is None else aliases
    raw = uploaded.read()
    for encoding in ('utf-8-sig', 'cp1252'):   # Excel's plain "CSV" is often Windows-1252
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportFileError('The file could not be read. Save it from Excel as "CSV UTF-8".')

    lookup = {}
    for field, header in columns:
        for alias in [header, field] + aliases.get(field, []):
            lookup.setdefault(_key(alias), field)
    for field in FLAG_FIELDS:
        for alias in [field] + ALIASES[field]:
            lookup.setdefault(_key(alias), field)

    reader = csv.reader(StringIO(text))
    fields = [lookup.get(_key(h)) for h in next(reader, [])]
    rows = []
    for number, cells in enumerate(reader, start=2):
        row = {f: (v or '').strip() for f, v in zip(fields, cells) if f}
        if any(row.values()):
            rows.append((number, row))
    return {f for f in fields if f}, rows


# ── Clients ────────────────────────────────────────────────────────────────────

def _clean_client_value(field, value):
    if field == 'island':
        return ISLANDS.get(value.lower(), value.title())
    if field == 'territory':
        return value.upper()
    if field == 'email':
        return value.lower()
    return value


def import_clients(uploaded):
    present, rows = read_rows(uploaded, CLIENT_COLUMNS)
    if 'customer_code' not in present or 'name' not in present:
        raise ImportFileError('The file needs "Customer Code" and "Name" columns. Download the template to see the format.')

    result = {'created': 0, 'updated': 0, 'unchanged': 0, 'linked': 0, 'skipped': [], 'renamed': []}
    editable = [f for f, _ in CLIENT_COLUMNS if f not in ('customer_code', 'name')] + list(FLAG_FIELDS)
    with transaction.atomic():
        for number, row in rows:
            code, name = row.get('customer_code', ''), ' '.join(row.get('name', '').split())[:255]
            label = f'Row {number} ({code or name or "blank"})'
            if not code:
                result['skipped'].append(f'{label}: Customer Code is required.')
                continue

            # The code is the key: a known code updates that client, including its name
            shop = Shop.objects.filter(customer_code__iexact=code).first()
            linked = False
            if shop is None and not name:
                result['skipped'].append(f'{label}: new code {code} needs a Name.')
                continue
            if shop is None:
                # A client from before codes existed: give it this code instead of making a duplicate
                shop = (Shop.objects.filter(name__iexact=name)
                        .filter(customer_code__isnull=True).order_by('id').first())
                linked = shop is not None
            is_new = shop is None
            if is_new:
                shop = Shop(name=name, contact_person=None, phone=None, address=None)
            if is_new or linked:
                shop.customer_code = code

            changed = False
            if name and shop.name != name and not is_new:
                result['renamed'].append(f'{code}: “{shop.name}” → “{name}”')
                shop.name = name
                changed = True
            for field in editable:
                if field not in present or not row.get(field):
                    continue   # blank cell or missing column: keep what's there
                if field in FLAG_FIELDS:
                    value = row[field].upper() in ('TRUE', 'YES', 'Y', '1')
                else:
                    value = _clean_client_value(field, row[field])[:Shop._meta.get_field(field).max_length]
                if getattr(shop, field) != value:
                    setattr(shop, field, value)
                    changed = True

            shop.save()
            if is_new:
                result['created'] += 1
            elif linked:
                result['linked'] += 1
            elif changed:
                result['updated'] += 1
            else:
                result['unchanged'] += 1
    return result


# ── Monthly sales ──────────────────────────────────────────────────────────────

MONTH_FORMATS = ('%Y-%m', '%Y/%m', '%m/%Y', '%m-%Y', '%b-%y', '%b-%Y', '%b %y', '%b %Y', '%B %Y', '%B-%Y', '%B %y',
                 '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d-%b-%y', '%d-%b-%Y', '%d %b %Y')


def parse_month(value):
    """'2026-09', 'Sep-26', 'September 2026', '09/2026', '01/09/2026' → date(2026, 9, 1)"""
    value = ' '.join(value.replace('.', '').split())
    for fmt in MONTH_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().replace(day=1)
        except ValueError:
            continue
    raise ValueError(f'"{value}" is not a month. Use e.g. 2026-09 or Sep-26')


def parse_money(value):
    """'WST 1,234.50', '$1,234.50', '(120.00)' (a negative) → Decimal"""
    text = re.sub(r'(?i)wst|\$|,|\s', '', value)
    negative = text.startswith('(') and text.endswith(')')
    amount = Decimal(text.strip('()'))
    if not amount.is_finite():
        raise InvalidOperation
    return -amount if negative else amount


def import_monthly_sales(uploaded):
    present, rows = read_rows(uploaded, SALES_COLUMNS)
    missing = [h for f, h in SALES_COLUMNS if f != 'customer_name' and f not in present]
    if missing:
        raise ImportFileError(f'The file needs these columns: {", ".join(missing)}. Download the template to see the format.')

    shops = {s.customer_code.casefold(): s for s in Shop.objects.exclude(customer_code__isnull=True)}
    result = {'created': 0, 'updated': 0, 'unchanged': 0, 'combined': 0, 'skipped': []}
    totals = {}   # (shop id, month) → the file's total for that client and month
    with transaction.atomic():
        for number, row in rows:
            code, name = row.get('customer_code', ''), row.get('customer_name', '')
            label = f'Row {number} ({code or name or "blank"})'
            shop = shops.get(code.casefold()) if code else None
            if shop is None:
                result['skipped'].append(f'{label}: no client has Customer Code "{code}". Upload it in Import Clients first.'
                                         if code else f'{label}: Customer Code is missing.')
                continue
            try:
                month = parse_month(row.get('month', ''))
            except ValueError as exc:
                result['skipped'].append(f'{label}: {exc}')
                continue
            try:
                amount = parse_money(row.get('sales', ''))
            except (InvalidOperation, ValueError):
                result['skipped'].append(f'{label}: Sales "{row.get("sales", "")}" is not a number.')
                continue
            # A client listed more than once for a month (e.g. one row per branch or invoice) is added up,
            # not overwritten by its last row
            key = (shop.pk, month)
            if key in totals:
                result['combined'] += 1
            totals[key] = totals.get(key, 0) + amount

        for (shop_id, month), amount in totals.items():
            record = MonthlySales.objects.filter(shop_id=shop_id, month=month).first()
            if record is None:
                MonthlySales.objects.create(shop_id=shop_id, month=month, sales=amount)
                result['created'] += 1
            elif record.sales != amount:
                record.sales = amount
                record.save(update_fields=['sales', 'updated_at'])
                result['updated'] += 1
            else:
                result['unchanged'] += 1
    return result
