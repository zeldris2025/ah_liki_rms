"""{% icon 'pin' %}: the portal's line icons as inline SVG (no icon font or CDN to load)."""
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# 24×24 stroke paths
PATHS = {
    'play':      '<rect x="2" y="5" width="20" height="14" rx="3"/><path d="m10 9 5 3-5 3z" fill="currentColor"/>',
    'pin':       '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    'building':  '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01'
                 'M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
    'people':    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
                 '<path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    'coins':     '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
                 '<path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>',
    'megaphone': '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    'chart':     '<path d="M3 3v18h18"/><path d="M7 16v-3M11 16V9M15 16v-5M19 16V6"/>',
    'box':       '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    'wrench':    '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91'
                 'a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    'briefcase': '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    'store':     '<path d="M3 9 4.5 4h15L21 9M3 9v11h18V9M3 9h18M9 20v-6h6v6"/>',
    'cart':      '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/>'
                 '<path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.6L21 7H6"/>',
    'utensils':  '<path d="M3 2v7a3 3 0 0 0 6 0V2M6 2v20M21 15V2a5 5 0 0 0-5 5v6a2 2 0 0 0 2 2h3zm0 0v7"/>',
    'leaf':      '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/>'
                 '<path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
    'burger':    '<path d="M4 11h16a1 1 0 0 0 1-1 8 8 0 0 0-18 0 1 1 0 0 0 1 1z"/><path d="M5 15v1a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3v-1"/>'
                 '<path d="M3 15a1 1 0 0 1 0-2h18a1 1 0 0 1 0 2z"/>',
    'coffee':    '<path d="M17 8h1a4 4 0 1 1 0 8h-1M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4z"/><path d="M6 2v2M10 2v2M14 2v2"/>',
    'drink':     '<path d="M5 2h14l-2 18a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2z"/><path d="M6 8h12"/>',
    'icecream':  '<path d="m7 11 4.08 10.35a1 1 0 0 0 1.84 0L17 11"/><path d="M17 7A5 5 0 0 0 7 7"/>'
                 '<path d="M17 7a2 2 0 0 1 0 4H7a2 2 0 0 1 0-4"/>',
    'wheat':     '<path d="M12 22V8"/><path d="M12 8C10 7 9 5 9 3c2 0 3 2 3 5zm0 0c2-1 3-3 3-5-2 0-3 2-3 5z"/>'
                 '<path d="M12 14c-2-1-4-2-5-4 2-.5 4 1 5 4zm0 0c2-1 4-2 5-4-2-.5-4 1-5 4z"/>'
                 '<path d="M12 19c-2-1-4-2-5-4 2-.5 4 1 5 4zm0 0c2-1 4-2 5-4-2-.5-4 1-5 4z"/>',
    'fish':      '<path d="M6.5 12c.94-3.46 4.94-6 8.5-6 3.56 0 6.06 2.54 7 6-.94 3.47-3.44 6-7 6s-7.56-2.53-8.5-6z"/>'
                 '<path d="M18 12v.5M7 10.67C7 8 5.58 5.97 2.73 5.5c-1 1.5-1 5 .23 6.5-1.24 1.5-1.24 5-.23 6.5'
                 'C5.58 18.03 7 16 7 13.33"/>',
    'tree':      '<path d="M12 2 6 10h3l-4 6h14l-4-6h3z"/><path d="M12 16v6"/>',
    'truck':     '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2M15 18H9M19 18h2a1 1 0 0 0 1-1v-3.65'
                 'a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>',
    'car':       '<path d="M19 17h2v-4l-2-5H5l-2 5v4h2"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M9 17h6M3 13h18"/>',
    'fuel':      '<path d="M3 22h12M4 9h10M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18"/>'
                 '<path d="M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 4 0V9.83a2 2 0 0 0-.59-1.42L18 5"/>',
    'plane':     '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5'
                 'c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>',
    'anchor':    '<circle cx="12" cy="5" r="3"/><path d="M12 22V8M5 12H2a10 10 0 0 0 20 0h-3"/>',
    'factory':   '<path d="M2 20V8l6 4V8l6 4V4h8v16z"/><path d="M17 20v-4M13 20v-4M9 20v-4"/>',
    'home':      '<path d="m3 10 9-7 9 7v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    'hammer':    '<path d="m14 6 4 4M3 21l9-9M12 3l9 9-3 3-9-9z"/>',
    'zap':       '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    'tag':       '<path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><path d="M7 7h.01"/>',
    'shirt':     '<path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10'
                 'c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>',
    'printer':   '<path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
                 '<rect x="6" y="14" width="12" height="8"/>',
    'laptop':    '<rect x="4" y="4" width="16" height="11" rx="2"/><path d="M2 20h20"/>',
    'headset':   '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1'
                 'a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
    'health':    '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/>',
    'heart':     '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2'
                 'A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7z"/>',
    'shield':    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    'book':      '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    'globe':     '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10'
                 ' 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    'star':      '<path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/>',
    'compass':   '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36z"/>',
    'arrow':     '<path d="M5 12h14M13 6l6 6-6 6"/>',
    'back':      '<path d="M19 12H5M11 18l-6-6 6-6"/>',
    'check':     '<path d="M20 6 9 17l-5-5"/>',
    'clock':     '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    'mail':      '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    'phone':     '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 '
                 '2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 '
                 '0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
    'external':  '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    'facebook':  '<path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/>',
    'instagram': '<rect x="2" y="2" width="20" height="20" rx="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 '
                 '11.37zM17.5 6.5h.01"/>',
    'linkedin':  '<path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z"/>'
                 '<rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/>',
}


# The icons a company or department can show on its card (the admin shows them as a picture grid)
BUSINESS_ICONS = [
    ('building', 'Building'), ('store', 'Store'), ('cart', 'Supermarket'), ('tag', 'Retail'), ('box', 'Warehouse'),
    ('truck', 'Delivery'), ('factory', 'Factory'), ('utensils', 'Restaurant'), ('burger', 'Fast food'),
    ('coffee', 'Café'), ('drink', 'Drinks'), ('icecream', 'Ice cream'), ('wheat', 'Bakery'), ('leaf', 'Farm'),
    ('tree', 'Plantation'), ('fish', 'Fishing'), ('car', 'Motors'), ('fuel', 'Fuel'), ('plane', 'Travel'),
    ('anchor', 'Shipping'), ('home', 'Property'), ('hammer', 'Construction'), ('wrench', 'Trades'), ('zap', 'Energy'),
    ('shirt', 'Clothing'), ('printer', 'Printing'), ('laptop', 'IT'), ('headset', 'Customer service'),
    ('coins', 'Finance'), ('chart', 'Sales'), ('megaphone', 'Marketing'), ('people', 'People / HR'),
    ('briefcase', 'Office'), ('health', 'Health'), ('heart', 'Care'), ('shield', 'Security'), ('book', 'Training'),
    ('globe', 'International'), ('star', 'Star'),
]


@register.simple_tag
def icon(name, size=24, cls='ic'):
    return format_html(
        '<svg class="{}" width="{}" height="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        cls, int(size), int(size), mark_safe(PATHS.get(name, PATHS['briefcase'])))


@register.simple_tag
def badge_icon(obj, size=24):
    """A company's uploaded icon if it has one, otherwise its chosen line icon."""
    url = getattr(obj, 'icon_url', '')
    if url:
        return format_html('<img class="icon-img" src="{}" alt="" width="{}" height="{}" loading="lazy">', url, int(size), int(size))
    return icon(obj.symbol, size)
