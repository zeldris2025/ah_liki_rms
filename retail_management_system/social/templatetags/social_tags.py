from django import template

register = template.Library()


@register.filter
def num(value):
    """12345 → '12,345'; nothing → '—'."""
    return '—' if value is None or value == '' else f'{value:,}'


@register.filter
def signed(value):
    """1234 → '+1,234', -5 → '−5', 0 → '0'."""
    if value is None:
        return '—'
    return f'+{value:,}' if value > 0 else (f'−{-value:,}' if value < 0 else '0')
