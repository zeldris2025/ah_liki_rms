"""CSV upload for sponsorships.

Safe to upload the same file again: a row matches an existing sponsorship on Customer + Type + Start date
(customer compared without case), and updates it instead of adding a duplicate. Customer names that match a
client or HORECA business are saved with that client's spelling. Blank cells never wipe existing values.
"""
from datetime import date, datetime
from decimal import InvalidOperation

from django.db import transaction

from .client_import import ImportFileError, finish, log, money, new_result, parse_money, read_rows, skip
from .models import Business, Shop, Sponsorship

# (field, CSV header) in the order the template uses
COLUMNS = [
    ('customer',         'Customer'),
    ('type',             'Type'),
    ('sponsorship_type', 'Sponsorship Type'),
    ('value',            'Value (WST)'),
    ('status',           'Status'),
    ('start',            'Start Date'),
    ('end',              'End Date'),
    ('notes',            'Notes'),
]
ALIASES = {
    'customer':         ['customername', 'client', 'clientname', 'shop', 'shopname', 'company', 'sponsor', 'name'],
    'type':             ['category', 'sponsorshipcategory', 'item'],
    'sponsorship_type': ['cashinkind', 'cashorinkind', 'valuetype', 'kind'],
    'value':            ['valuewst', 'amount', 'total', 'wst', 'cost'],
    'start':            ['startdate', 'from', 'begin'],
    'end':              ['enddate', 'to', 'expiry', 'expirydate', 'finish'],
    'notes':            ['note', 'comments', 'comment', 'description', 'details'],
}
DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%b-%y', '%d-%b-%Y', '%d %b %Y', '%d %B %Y')
# Other spellings for the Cash / In-Kind choice
SPONSORSHIP_TYPES = {'cash': 'Cash Value', 'cashvalue': 'Cash Value',
                     'inkind': 'In-Kind Value', 'inkindvalue': 'In-Kind Value', 'kind': 'In-Kind Value'}
EDITABLE = [f for f, _ in COLUMNS if f != 'customer']


def parse_date(value):
    """'2026-10-01', '01/10/2026' (day first), '1-Oct-26' → date(2026, 10, 1)"""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'"{value}" is not a date. Use YYYY-MM-DD, e.g. 2026-10-01')


def _choice(field, value):
    """Match a choice without case or punctuation, e.g. 'cooler' → 'Cooler', 'in kind' → 'In-Kind Value'."""
    choices = Sponsorship._meta.get_field(field).choices
    key = ''.join(c for c in value.lower() if c.isalnum())
    for stored, _ in choices:
        if ''.join(c for c in stored.lower() if c.isalnum()) == key:
            return stored
    if field == 'sponsorship_type' and key in SPONSORSHIP_TYPES:
        return SPONSORSHIP_TYPES[key]
    raise ValueError(f'{field.replace("_", " ").title()} "{value}" must be one of: '
                     f'{", ".join(c for c, _ in choices)}.')


def _clean(field, value):
    if field in ('type', 'sponsorship_type', 'status'):
        return _choice(field, value)
    if field == 'value':
        try:
            return parse_money(value)
        except (InvalidOperation, ValueError):
            raise ValueError(f'Value "{value}" is not a number.')
    if field in ('start', 'end'):
        return parse_date(value)
    return value


def _show(value):
    if value in (None, ''):
        return 'blank'
    if isinstance(value, date):
        return f'{value:%Y-%m-%d}'
    return value if isinstance(value, str) else money(value)


def import_sponsorships(uploaded):
    present, rows = read_rows(uploaded, COLUMNS, ALIASES)
    if 'customer' not in present:
        raise ImportFileError('The file needs a "Customer" column. Download the template to see the format.')

    # Use the spelling of a known client or business, so the same customer isn't listed two ways
    known = {}
    for name in list(Business.objects.values_list('name', flat=True)) + list(Shop.objects.values_list('name', flat=True)):
        known.setdefault(' '.join(name.split()).casefold(), name)

    result = new_result()
    with transaction.atomic():
        for number, row in rows:
            customer = ' '.join(row.get('customer', '').split())
            customer = known.get(customer.casefold(), customer)[:200]
            if not customer:
                skip(result, number, '', 'Customer is required.')
                continue
            try:
                values = {f: _clean(f, row[f]) for f in EDITABLE if row.get(f)}
            except ValueError as exc:
                skip(result, number, customer, str(exc))
                continue
            if values.get('start') and values.get('end') and values['end'] < values['start']:
                skip(result, number, customer, 'End Date is before Start Date.')
                continue

            sp_type = values.get('type', Sponsorship._meta.get_field('type').default)
            sponsorship = Sponsorship.objects.filter(customer__iexact=customer, type=sp_type,
                                                     start=values.get('start')).order_by('id').first()
            item = f'{customer} · {sp_type}' + (f' · from {values["start"]:%Y-%m-%d}' if values.get('start') else '')
            if sponsorship is None:
                Sponsorship.objects.create(customer=customer, **values)
                result['created'] += 1
                detail = ', '.join(f'{label} {_show(values[f])}' for f, label in COLUMNS
                                   if f in values and f not in ('type', 'start', 'notes'))
                log(result, 'added', number, item, detail or 'New sponsorship')
                continue

            changes = []
            for field, value in values.items():
                old = getattr(sponsorship, field)
                if old != value:
                    label = dict(COLUMNS)[field]
                    changes.append(f'{label}: {_show(old)} → {_show(value)}')
                    setattr(sponsorship, field, value)
            if changes:
                sponsorship.save()
                result['updated'] += 1
                log(result, 'updated', number, item, '; '.join(changes))
            else:
                result['unchanged'] += 1
                log(result, 'unchanged', number, item)
    return finish(result)
