"""Corporate sales streams: who looks after which clients, and their actual sales against target.

The reps (Grace, Ruth, …) are Sales Rep records edited in the admin panel. A client belongs to a rep
when its Customer Type (from the client CSV upload) contains one of the rep's keywords, ignoring
case, so "Ministry of Health", "MINISTRIES" and "Govt Ministry" all count for the rep with "ministr".
"""
from datetime import date

from django.db.models import Max, Sum

from .models import CustomerProductSales, MonthlySales, SalesRep, SalesTarget, Shop

MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def month_span(indexes):
    """[0, 1, 2, 5] -> 'Jan–Mar, Jun' (month indexes 0-11)"""
    parts, run = [], []
    for i in sorted(indexes):
        if run and i != run[-1] + 1:
            parts.append(run)
            run = []
        run.append(i)
    if run:
        parts.append(run)
    return ', '.join(MONTH_LABELS[r[0]] if len(r) == 1 else f'{MONTH_LABELS[r[0]]}–{MONTH_LABELS[r[-1]]}' for r in parts)


def managers():
    """Active reps in page order, as dicts: key, name, color, streams (list)."""
    return [{'key': r.key, 'name': r.name, 'color': r.color, 'streams': r.stream_list(), 'rep': r}
            for r in SalesRep.objects.filter(active=True)]


def own_rep_key(user):
    """The rep key a logged-in rep is limited to, or None when they see every stream (Managers, and staff who
    aren't a rep). A rep sees only their own stream, plus everyone's % of this month's target."""
    from .access import MANAGER, roles_of
    if not user.is_authenticated or MANAGER in roles_of(user):
        return None
    rep = SalesRep.objects.filter(user=user, active=True).first()
    return rep.key if rep else None


def manager_keys():
    return list(SalesRep.objects.filter(active=True).values_list('key', flat=True))


def manager_for_type(customer_type, reps=None):
    """The key of the first rep (in page order) whose keywords match a customer type, or None."""
    for r in (reps if reps is not None else SalesRep.objects.filter(active=True)):
        if r.matches(customer_type):
            return r.key
    return None


def client_ids_by_manager():
    """{manager key: [shop ids]} plus the customer types that matched no stream."""
    reps = list(SalesRep.objects.filter(active=True))
    ids = {r.key: [] for r in reps}
    types = {r.key: set() for r in reps}
    unmatched = set()
    owner = {}   # each distinct customer type is only matched once
    for pk, ctype in Shop.objects.exclude(customer_type='').values_list('id', 'customer_type'):
        if ctype not in owner:
            owner[ctype] = manager_for_type(ctype, reps)
        key = owner[ctype]
        if key:
            ids[key].append(pk)
            types[key].add(ctype)
        else:
            unmatched.add(ctype)
    return ids, types, sorted(unmatched)


def top_products(shop_ids, year, limit=10):
    """The best-selling products for these clients in a year, from the Customer Product Sales upload."""
    rows = (CustomerProductSales.objects.filter(month__year=year, shop_id__in=shop_ids)
            .values('product_code').annotate(total=Sum('sales'), name=Max('product_name')).order_by('-total')[:limit])
    return [{'code': r['product_code'], 'name': r['name'], 'value': float(r['total'])} for r in rows]


def year_summary(year, today=None):
    """Actual and target per month for each manager, plus the figures for their card."""
    today = today or date.today()
    current_month = today.month if today.year == year else (12 if year < today.year else 0)
    ids, types, unmatched = client_ids_by_manager()

    reps = managers()
    targets = {m['key']: [None] * 12 for m in reps}
    for t in SalesTarget.objects.filter(month__year=year, manager__in=list(targets)):
        targets[t.manager][t.month.month - 1] = t.amount

    summary = []
    for m in reps:
        actual = [None] * 12
        rows = (MonthlySales.objects.filter(month__year=year, shop_id__in=ids[m['key']])
                .values('month').annotate(total=Sum('sales')))
        for r in rows:
            actual[r['month'].month - 1] = r['total']
        previous = [None] * 12   # the same months last year, for the year-on-year comparison on the graph
        for r in (MonthlySales.objects.filter(month__year=year - 1, shop_id__in=ids[m['key']])
                  .values('month').annotate(total=Sum('sales'))):
            previous[r['month'].month - 1] = r['total']
        done = range(current_month)   # months that have started this year
        ytd_actual = sum(actual[i] or 0 for i in done)
        # Compare like with like: only months that have a target count towards the YTD %
        targeted = [i for i in done if targets[m['key']][i] is not None]
        ytd_target = sum(targets[m['key']][i] for i in targeted)
        ytd_actual_on_target = sum(actual[i] or 0 for i in targeted)
        # last year's sales over the same months the YTD actual counts, the financial target on the All table
        ytd_previous = sum(previous[i] or 0 for i in (targeted if ytd_target else done))
        month_i = current_month - 1
        top = (MonthlySales.objects.filter(month__year=year, shop_id__in=ids[m['key']])
               .values('shop_id', 'shop__name').annotate(total=Sum('sales')).order_by('-total')[:5])
        summary.append({
            **m,
            'actual': actual,
            'previous': previous,
            'target': targets[m['key']],
            'client_count': len(ids[m['key']]),
            'client_ids': ids[m['key']],
            'types': sorted(types[m['key']]),
            'ytd_actual': ytd_actual,
            'ytd_target': ytd_target,
            'ytd_actual_on_target': ytd_actual_on_target,
            'ytd_previous': ytd_previous,
            'ytd_pct': round(ytd_actual_on_target / ytd_target * 100) if ytd_target else None,
            'ytd_target_months': month_span(targeted),
            'ytd_missing_months': month_span([i for i in done if i not in targeted]),
            'ytd_months': month_span(list(done)),
            'month_label': f'{MONTH_LABELS[month_i]} {year}' if month_i >= 0 else '',
            'month_actual': actual[month_i] or 0 if month_i >= 0 else 0,
            'month_previous': previous[month_i] or 0 if month_i >= 0 else 0,
            'month_target': targets[m['key']][month_i] if month_i >= 0 else None,
            'top_clients': list(top),
        })
    for m in summary:
        m['month_pct'] = round(m['month_actual'] / m['month_target'] * 100) if m['month_target'] else None
    return summary, unmatched


def combined_summary(summary):
    """Every stream together, for the All slide: monthly totals for the graph, and a row per stream for the
    table of actual against target (year to date and the current month). Like the cards, year to date only
    counts the months that have a target."""
    def total(values):
        values = [v for v in values if v is not None]
        return sum(values) if values else None

    def row(m, actual, financial, target):
        variance = actual - target if target else None
        fin_variance = actual - financial if financial else None
        return {'key': m['key'], 'name': m['name'], 'color': m['color'], 'stream': ' / '.join(m['streams']),
                'actual': actual, 'financial': financial, 'target': target, 'variance': variance,
                'variance_pct': round(variance / target * 100, 1) if target else None,
                'fin_variance': fin_variance,
                'fin_variance_pct': round(fin_variance / financial * 100, 1) if financial else None}

    def table(rows):
        rows = [r for r in rows if r['actual']]   # streams with no sales in the period are left off the table
        # a stream without a target still adds its sales to the total, but not to the variance
        target = sum(r['target'] or 0 for r in rows) or None
        variance = sum(r['variance'] for r in rows if r['variance'] is not None) if target else None
        # the financial target (last year's sales) works the same way: streams with no sales last year are left out
        financial = sum(r['financial'] or 0 for r in rows) or None
        fin_variance = sum(r['fin_variance'] for r in rows if r['fin_variance'] is not None) if financial else None
        return rows, {'actual': sum(r['actual'] for r in rows), 'financial': financial,
                      'fin_variance': fin_variance,
                      'fin_variance_pct': round(fin_variance / financial * 100, 1) if financial else None,
                      'target': target, 'variance': variance,
                      'variance_pct': round(variance / target * 100, 1) if target else None,
                      'untargeted': [r['name'] for r in rows if not r['target']]}

    first = summary[0] if summary else {}
    ytd_rows, ytd_total = table([row(m, m['ytd_actual_on_target'] if m['ytd_target'] else m['ytd_actual'],
                                     m['ytd_previous'], m['ytd_target'] or None) for m in summary])
    month_rows, month_total = table([row(m, m['month_actual'] or 0, m['month_previous'], m['month_target'] or None) for m in summary])
    return {
        'actual': [total(m['actual'][i] for m in summary) for i in range(12)],
        'previous': [total(m['previous'][i] for m in summary) for i in range(12)],
        'target': [total(m['target'][i] for m in summary) for i in range(12)],
        'streams': [' / '.join(m['streams']) for m in summary],
        'client_count': sum(m['client_count'] for m in summary),
        'month_label': first.get('month_label', ''),
        'ytd_months': first.get('ytd_months', ''),
        'missing': [f"{m['name']} ({m['ytd_missing_months']})" for m in summary if m['ytd_target'] and m['ytd_missing_months']],
        # the table's two periods; year to date shows first
        'tables': [t for t in (
            {'key': 'ytd', 'label': f"Year to date · {first.get('ytd_months', '')}", 'rows': ytd_rows, 'total': ytd_total},
            {'key': 'month', 'label': first.get('month_label', ''), 'rows': month_rows, 'total': month_total},
        ) if first.get('month_label')],
    }
