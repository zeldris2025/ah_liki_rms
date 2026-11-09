from django import template

register = template.Library()


@register.filter
def qty(value):
    """1234.5 → '1,234.5', 1200 → '1,200'; nothing → '—'."""
    if value is None or value == '':
        return '—'
    return f'{value:,.2f}'.rstrip('0').rstrip('.')


@register.filter
def signed_qty(value):
    """120 → '+120', -5 → '−5', 0 → '0'."""
    if value is None:
        return '—'
    return f'+{qty(value)}' if value > 0 else (f'−{qty(-value)}' if value < 0 else '0')


@register.filter
def bar(value, biggest):
    """A value as a % of the largest one, for the inline bars."""
    try:
        return round(float(value or 0) / float(biggest) * 100, 1) if biggest else 0
    except (TypeError, ValueError):
        return 0
