"""CSV upload for Social #s: one row per company per update day.

Safe to upload the same file again: a row matches the numbers already saved for its Company + Date and updates
them instead of adding a duplicate. Company names are matched without case, spaces or punctuation (and a few
short forms, e.g. 'Ink Pro' or 'NSW'). Dates must be Mondays or Saturdays, not in the future. Blank cells never
wipe a number that's already saved.
"""
from django.db import transaction

from shops.client_import import ImportFileError, _key, finish, log, new_result, read_rows, skip
from shops.sponsorship_import import parse_date

from .models import COMPANIES, PLATFORMS, SocialCount, is_update_day, office_today

# (field, CSV header) in the order the template uses
COLUMNS = [
    ('date',      'Date'),
    ('company',   'Company'),
    ('facebook',  'Facebook'),
    ('instagram', 'Instagram'),
]
ALIASES = {
    'date':      ['day', 'updatedate', 'updated', 'asof', 'asat'],
    'company':   ['companyname', 'business', 'brand', 'page', 'name'],
    'facebook':  ['fb', 'facebookfollowers', 'fbfollowers', 'facebooklikes', 'fblikes'],
    'instagram': ['ig', 'insta', 'instagramfollowers', 'igfollowers'],
}
# Other ways people write the company names (compared as _key: lower case, letters and digits only)
COMPANY_ALIASES = {
    'ahliki': 'ah_liki_wholesale', 'ahlikiwholesale': 'ah_liki_wholesale', 'aliki': 'ah_liki_wholesale',
    'farmerjoe': 'farmer_joe', 'farmerjoes': 'farmer_joe', 'fj': 'farmer_joe',
    'burgerbills': 'burger_bills', 'burgerbill': 'burger_bills', 'bb': 'burger_bills',
    'naturalsamoawater': 'natural_samoa_water', 'naturalsamoa': 'natural_samoa_water', 'nsw': 'natural_samoa_water',
    'inkpro': 'ink_pro',
}
for _company, _name in COMPANIES:
    COMPANY_ALIASES.setdefault(_key(_name), _company)
NAMES = dict(COMPANIES)


def _company(value):
    company = COMPANY_ALIASES.get(_key(value))
    if not company:
        raise ValueError(f'Company "{value}" must be one of: {", ".join(NAMES.values())}.')
    return company


def _followers(label, value):
    """'5,200' or '5200' → 5200"""
    text = value.replace(',', '').replace(' ', '')
    if not text.isdigit():
        raise ValueError(f'{label} "{value}" is not a whole number.')
    return int(text)


def _show(value):
    return 'blank' if value is None else f'{value:,}'


def import_social_numbers(uploaded, user):
    present, rows = read_rows(uploaded, COLUMNS, ALIASES)
    missing = [header for field, header in COLUMNS[:2] if field not in present]
    if missing:
        raise ImportFileError(f'The file needs {" and ".join(f"a {h!r} column" for h in missing)}. '
                              'See the CSV columns for the format.')
    if not {'facebook', 'instagram'} & present:
        raise ImportFileError('The file needs a "Facebook" or an "Instagram" column.')

    today = office_today()
    result = new_result()
    with transaction.atomic():
        for number, row in rows:
            item = ' · '.join(v for v in (row.get('company'), row.get('date')) if v)
            try:
                if not row.get('company'):
                    raise ValueError('Company is required.')
                company = _company(row['company'])
                if not row.get('date'):
                    raise ValueError('Date is required.')
                day = parse_date(row['date'])
                if not is_update_day(day):
                    raise ValueError(f'{day:%A %Y-%m-%d} isn’t an update day (Mondays and Saturdays only).')
                if day > today:
                    raise ValueError(f'{day:%Y-%m-%d} hasn’t come yet.')
                values = {p: _followers(label, row[p]) for p, label in PLATFORMS if row.get(p)}
            except ValueError as exc:
                skip(result, number, item, str(exc))
                continue
            item = f'{NAMES[company]} · {day:%a %Y-%m-%d}'
            if not values:
                skip(result, number, item, 'No Facebook or Instagram number.')
                continue

            count = SocialCount.objects.filter(company=company, date=day).first()
            if count is None:
                SocialCount.objects.create(company=company, date=day, updated_by=user, **values)
                result['created'] += 1
                log(result, 'added', number, item,
                    ', '.join(f'{label} {_show(values[p])}' for p, label in PLATFORMS if p in values))
                continue
            changes = [f'{label}: {_show(getattr(count, p))} → {_show(values[p])}'
                       for p, label in PLATFORMS if p in values and getattr(count, p) != values[p]]
            if changes:
                for p, value in values.items():
                    setattr(count, p, value)
                count.updated_by = user
                count.save()
                result['updated'] += 1
                log(result, 'updated', number, item, '; '.join(changes))
            else:
                result['unchanged'] += 1
                log(result, 'unchanged', number, item)
    return finish(result)
