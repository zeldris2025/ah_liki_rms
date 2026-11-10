"""English / Samoan on the public Career Connect pages (see career_connect/i18n.py).

{% t "Apply now" %}                        the text in the page's language
{% t "Closes {date}" date=d %}             with {placeholders} filled in
{% tp n "{n} Role" "{n} Roles" %}           singular or plural (Samoan uses one form)
{% cc_date role.expires_on "j M Y" %}      a date with Samoan month names in Samoan
{% lang_switch_url %}                      the link the language button goes to
"""
from urllib.parse import urlencode

from django import template
from django.urls import reverse

from .. import i18n

register = template.Library()


def _lang(context):
    return context.get('cc_lang', i18n.ENGLISH)


@register.simple_tag(takes_context=True)
def t(context, text, **values):
    return i18n.translate(text, _lang(context), **values)


@register.simple_tag(takes_context=True)
def tp(context, n, singular, plural_text, **values):
    return i18n.plural(n, singular, plural_text, _lang(context), **values)


@register.simple_tag(takes_context=True)
def cc_date(context, value, fmt):
    return i18n.format_date(value, fmt, _lang(context))


@register.simple_tag(takes_context=True)
def lang_switch_url(context):
    other = i18n.ENGLISH if _lang(context) == i18n.SAMOAN_CODE else i18n.SAMOAN_CODE
    request = context.get('request')
    query = {'to': other}
    if request is not None:
        query['next'] = request.get_full_path()
    return reverse('career_connect_language') + '?' + urlencode(query)
