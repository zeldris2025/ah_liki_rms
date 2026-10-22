import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from shops.models import Shop

from .gazetteer import SAVAII_CENTER, UPOLU_CENTER, locate
from .models import ShopLocation

# Generous box around Upolu, Savaii, Manono and Apolima; rejects stray clicks.
SAMOA_BOUNDS = {'south': -14.20, 'north': -13.30, 'west': -172.85, 'east': -171.30}

UNASSIGNED = 'Unassigned'


def _shop_payload(shop):
    loc = getattr(shop, 'atlas_location', None)
    if loc:
        lat, lng, manual = float(loc.latitude), float(loc.longitude), True
    else:
        lat, lng = locate(shop.address) or (None, None)
        manual = False
    return {
        'id':        shop.id,
        'name':      shop.name,
        'address':   shop.address if shop.address and shop.address.lower() != 'n/a' else '',
        'owner':     shop.contact_person if shop.contact_person and shop.contact_person.lower() != 'n/a' else '',
        'phone':     shop.phone if shop.phone and shop.phone.lower() != 'n/a' else '',
        'island':    shop.island,
        'territory': shop.territory or UNASSIGNED,
        'tip_top':   shop.tip_top,
        'taula':     shop.taula_fridge,
        'talofa':    shop.talofa_voucher,
        'faakau':    shop.faakau_com,
        'lat':       lat,
        'lng':       lng,
        'manual':    manual,
        'url':       reverse('shop_detail', args=[shop.id]),
        'pin_url':   reverse('atlas_shop_location', args=[shop.id]),
    }


@login_required(login_url='login')
def atlas(request):
    shops = [_shop_payload(s) for s in Shop.objects.select_related('atlas_location').order_by('name')]
    territories = [code for code, _ in Shop.TERRITORY_CHOICES]
    if any(s['territory'] == UNASSIGNED for s in shops):
        territories.append(UNASSIGNED)
    return render(request, 'retail_atlas/atlas.html', {
        'atlas_data': {
            'shops':       shops,
            'territories': territories,
            'upolu':       UPOLU_CENTER,
            'savaii':      SAVAII_CENTER,
            'bounds':      SAMOA_BOUNDS,
            'is_fe':       request.is_fe,
            'read_only':   getattr(request, 'is_finance', False),   # Finance look but don't touch
            'order_url':   reverse('fe_place_order'),
        },
    })


@login_required(login_url='login')
@require_POST
def shop_location(request, shop_id):
    """Pin a shop to a clicked point (`{"lat", "lng"}`) or drop the pin (`{"reset": true}`)."""
    shop = get_object_or_404(Shop, id=shop_id)
    try:
        body = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if body.get('reset'):
        ShopLocation.objects.filter(shop=shop).delete()
        shop.atlas_location = None
        return JsonResponse(_shop_payload(shop))

    try:
        lat, lng = float(body['lat']), float(body['lng'])
    except (KeyError, TypeError, ValueError):
        return JsonResponse({'error': 'lat and lng are required numbers'}, status=400)
    b = SAMOA_BOUNDS
    if not (b['south'] <= lat <= b['north'] and b['west'] <= lng <= b['east']):
        return JsonResponse({'error': 'That point is outside Samoa'}, status=400)

    loc, _ = ShopLocation.objects.update_or_create(
        shop=shop,
        defaults={'latitude': round(lat, 6), 'longitude': round(lng, 6),
                  'updated_by': request.user.get_username()},
    )
    shop.atlas_location = loc
    return JsonResponse(_shop_payload(shop))
