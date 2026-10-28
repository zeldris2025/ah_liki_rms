"""The QR code students scan: it holds the public Career Connect address and nothing else."""
import io
import ipaddress
from urllib.parse import urlparse

import segno
from django.conf import settings


def portal_url():
    """CAREER_CONNECT_URL if set, else SITE_URL + /career-connect/."""
    return settings.CAREER_CONNECT_URL


def url_problems(url):
    """Reasons this address shouldn't be printed (empty list when it's a proper public HTTPS address)."""
    u = urlparse(url)
    host = (u.hostname or '').lower()
    problems = []
    if u.scheme != 'https':
        problems.append('it is not an HTTPS address')
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_link_local:
            problems.append(f'{host} is a private/local network address that phones outside the office can\'t reach')
    except ValueError:
        if host in ('localhost', '') or host.endswith(('.local', '.localhost')):
            problems.append(f'"{host or "(none)"}" is a development address')
    if not u.path.rstrip('/').endswith('/career-connect'):
        problems.append('it does not end in /career-connect/')
    return problems


def make(url=None):
    return segno.make(url or portal_url(), error='m', micro=False)


def png_bytes(url=None, scale=16):
    buf = io.BytesIO()
    make(url).save(buf, kind='png', scale=scale, border=4, dark='#0B1F3A')
    return buf.getvalue()


def svg_bytes(url=None):
    buf = io.BytesIO()
    make(url).save(buf, kind='svg', scale=10, border=4, dark='#0B1F3A', xmldecl=True)
    return buf.getvalue()


def png_data_uri(url=None):
    return make(url).png_data_uri(scale=8, border=4, dark='#0B1F3A')
