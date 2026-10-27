import csv
import json
import os
import re
import zipfile
from datetime import date
from decimal import InvalidOperation
from io import StringIO, BytesIO

from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q, Sum, Count, Avg, F, Max, Min, OuterRef, Subquery, DecimalField
from django.db import models, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode

from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from tablib import Dataset

from .models import Business, BusinessPhoto, Shop, ShopPhoto, Sponsorship, SponsorshipPhoto, Survey, SurveyResponse, MonthlySales, Promotion, SalesTarget, PinnedProduct, ProductGroup, ProductSales, QuickLinkTarget
from .forms import BusinessCSVImportForm, SurveyForm, SurveyResponseForm, BulkSurveyResponseForm
from . import access, analytics, client_import, corporate, product_sales, sponsorship_import
from .admin import BusinessResource


# ── helpers ───────────────────────────────────────────────────────────────────

def _photo_data(p):
    return {'id': p.pk, 'url': p.image.url, 'note': p.note}


# ══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════

def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
    else:
        form = AuthenticationForm()
    
    return render(request, 'shops/login.html', {'form': form})


def user_logout(request):
    logout(request)
    return redirect('login')


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def dashboard(request):
    if getattr(request, 'is_finance', False):
        from car_allocations.views import finance_dashboard
        return finance_dashboard(request)
    shops        = Shop.objects.prefetch_related('photos').all()
    businesses   = Business.objects.prefetch_related('photos').all()
    sponsorships = Sponsorship.objects.prefetch_related('photos').all()

    active_spons = sponsorships.filter(status='Active')
    total_photos = ShopPhoto.objects.count()
    shops_with_photos = shops.filter(photos__isnull=False).distinct().count()

    territory_data = [
        {'label': t, 'value': shops.filter(territory=t).count()}
        for t in ['EC1', 'EC2', 'EC3', 'LFG', 'VT1', 'VT2', 'VT3', 'WC1', 'WC2', 'WC4']
    ]
    # Corporate sales by customer type: this year's sales per type, coloured by the rep who looks after it
    sales_year = date.today().year
    _, types_by_rep, _ = corporate.client_ids_by_manager()
    reps = corporate.managers()
    corp_sales = {r['shop__customer_type']: (r['total'], r['clients']) for r in
                  MonthlySales.objects.filter(month__year=sales_year,
                                              shop__customer_type__in=[t for ts in types_by_rep.values() for t in ts])
                  .values('shop__customer_type').annotate(total=Sum('sales'), clients=Count('shop', distinct=True))}
    client_counts = dict(Shop.objects.values_list('customer_type').annotate(n=Count('id')))
    biz_data = sorted(({'label': t, 'value': float(corp_sales.get(t, (0, 0))[0] or 0), 'rep': r['name'], 'key': r['key'],
                        'color': r['color'], 'clients': client_counts.get(t, 0)}
                       for r in reps for t in types_by_rep[r['key']]), key=lambda d: -d['value'])
    recent_shops = list(shops.order_by('-id')[:6])

    # FE ordering
    from fe_orders.models import Order, Product
    # Local midnight on this computer's clock (settings.TIME_ZONE is UTC, 13 hours off Samoa)
    from datetime import datetime
    local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    recent_orders = list(Order.objects.select_related('shop', 'placed_by').prefetch_related('items')[:6])
    telegram_failed = Order.objects.filter(telegram_status__startswith='Failed').count()
    whatsapp_failed = Order.objects.filter(whatsapp_status__startswith='Failed').count()

    # Promotions: running now first, then the next ones to start
    live_promos = list(Promotion.objects.filter(Promotion.status_q('Active')).order_by('end_date', 'name'))
    upcoming_promos = list(Promotion.objects.filter(Promotion.status_q('Upcoming')).order_by('start_date', 'name'))

    ctx = {
        'shops': shops,
        'businesses': businesses,
        'sponsorships': sponsorships,
        'active_spons': active_spons,
        'active_val': float(active_spons.aggregate(v=Sum('value'))['v'] or 0),
        'total_photos': total_photos,
        'shops_with_photos': shops_with_photos,
        'tip_top_count': shops.filter(tip_top=True).count(),
        'region_data': json.dumps(territory_data),
        'biz_data': json.dumps(biz_data),
        'corp_reps': reps, 'sales_year': sales_year,
        'recent_shops': recent_shops,
        'recent_orders': recent_orders,
        'corporate_clients': sum(len(ids) for ids in corporate.client_ids_by_manager()[0].values()),
        'pending_orders': Order.objects.filter(status='Pending').count(),
        'orders_today': Order.objects.filter(created_at__gte=local_midnight).count(),
        'telegram_failed': telegram_failed,
        'whatsapp_failed': whatsapp_failed,
        'out_of_stock': Product.objects.filter(available=False).count(),
        'product_count': Product.objects.count(),
        'live_promos': live_promos,
        'upcoming_promos': upcoming_promos,
        'dashboard_promos': (live_promos + upcoming_promos)[:6],
    }
    # Leave out figures from areas this access level can't open (the page's JS would otherwise still carry them)
    blocked = request.blocked_areas
    if 'corporate_sales' in blocked:
        ctx.update(biz_data='[]', corp_reps=[], corporate_clients=0)
    else:
        own = corporate.own_rep_key(request.user)
        if own:   # a rep sees only their own stream
            ctx.update(biz_data=json.dumps([d for d in biz_data if d['key'] == own]),
                       corp_reps=[r for r in reps if r['key'] == own],
                       corporate_clients=len(corporate.client_ids_by_manager()[0].get(own, [])))
    if 'fe_ordering' in blocked:
        ctx.update(recent_orders=[], pending_orders=0, orders_today=0, telegram_failed=0, whatsapp_failed=0, out_of_stock=0, product_count=0)
    if 'promotions' in blocked:
        ctx.update(live_promos=[], upcoming_promos=[], dashboard_promos=[])
    if 'sponsorships' in blocked:
        ctx.update(sponsorships=Sponsorship.objects.none(), active_spons=Sponsorship.objects.none(), active_val=0)
    return render(request, 'shops/dashboard.html', ctx)


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS (Managers)
# ══════════════════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def analytics_page(request):
    """Will each corporate stream reach its target, how each rep is doing, and average sales per day.
    ?month=YYYY-MM picks the month (the latest with sales by default); ?forecast=1 opens the target check."""
    months = analytics.available_months()
    month = months[0] if months else date.today().replace(day=1)
    try:
        picked = date.fromisoformat((request.GET.get('month') or '') + '-01')
        if picked in months:
            month = picked
    except ValueError:
        pass
    data = analytics.month_analysis(month)
    return render(request, 'shops/analytics.html', {
        **data, 'months': months, 'show_forecast': request.GET.get('forecast') == '1',
        'trend_json': json.dumps(data['trend']),
        'updated_as_of': MonthlySales.objects.aggregate(last=Max('updated_at'))['last'],
    })


# ══════════════════════════════════════════════════════════════════════════════
# SHOPS
# ══════════════════════════════════════════════════════════════════════════════

SHOP_TERRITORIES = ['EC1', 'EC2', 'EC3', 'LFG', 'VT1', 'VT2', 'VT3', 'WC1', 'WC2', 'WC4']
EXTRA_CUSTOMER_TYPES = ['Fe Regions', 'Inkpro']   # offered in the client form even before any client uses them


def customer_type_choices():
    """Every customer type in use (from the client upload) plus the extra ones, for the client form dropdown."""
    used = Shop.objects.exclude(customer_type='').values_list('customer_type', flat=True).distinct()
    return sorted(set(used) | set(EXTRA_CUSTOMER_TYPES), key=str.lower)


def shop_list(request):
    qs = Shop.objects.prefetch_related('photos').all()

    q           = request.GET.get('q', '').strip()
    territories = request.GET.getlist('territory')
    tip_top     = request.GET.get('tip_top', '')
    taula       = request.GET.get('taula_fridge', '')
    talofa      = request.GET.get('talofa_voucher', '')
    faakau      = request.GET.get('faakau_com', '')
    photos      = request.GET.get('photos', '')
    ctypes      = [t for t in request.GET.getlist('customer_type') if t]
    island      = request.GET.get('island', '')

    if island:
        qs = qs.filter(island=island)
    if ctypes:
        # Several types combine with OR; "__none__" stands for clients with no type set
        named = [t for t in ctypes if t != '__none__']
        qs = qs.filter(Q(customer_type__in=named) | (Q(customer_type='') if '__none__' in ctypes else Q(pk__in=[])))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(customer_code__iexact=q) | Q(contact_person__icontains=q)
                       | Q(address__icontains=q))
    if territories:
        # "OTHER" catches everything the listed territory checkboxes miss:
        # unlisted codes plus shops with no territory recorded.
        named = [t for t in territories if t != 'OTHER']
        territory_q = Q()
        if named:
            territory_q |= Q(territory__in=named)
        if 'OTHER' in territories:
            territory_q |= (~Q(territory__in=SHOP_TERRITORIES) |
                            Q(territory__isnull=True) | Q(territory=''))
        qs = qs.filter(territory_q)
    # Programme filters combine with OR: picking Tip Top = Yes and Taula Fridge = Yes
    # shows shops in either programme, not only those in both.
    programme = Q()
    for field, value in (('tip_top', tip_top), ('taula_fridge', taula),
                         ('talofa_voucher', talofa), ('faakau_com', faakau)):
        if value == 'yes':
            programme |= Q(**{field: True})
        elif value == 'no':
            programme |= Q(**{field: False})
    if programme:
        qs = qs.filter(programme)
    if photos == 'yes':
        qs = qs.filter(photos__isnull=False).distinct()
    elif photos == 'no':
        qs = qs.filter(photos__isnull=True)

    # Total sales this year so far, as a subquery so joins used by other filters can't double it
    sales_year = date.today().year
    year_total = (MonthlySales.objects.filter(shop=OuterRef('pk'), month__year=sales_year)
                  .values('shop').annotate(t=Sum('sales')).values('t'))
    qs = qs.annotate(total_sales=Subquery(year_total, output_field=DecimalField(max_digits=14, decimal_places=2)))
    sort = request.GET.get('sort', '')
    if sort in ('sales', 'sales_low') and not access.can_see_sales(request):
        sort = ''
    if sort == 'sales':
        qs = qs.order_by(F('total_sales').desc(nulls_last=True), 'name')
    elif sort == 'sales_low':
        qs = qs.order_by(F('total_sales').asc(nulls_first=True), 'name')

    paginator = Paginator(qs, 12)
    page_obj  = paginator.get_page(request.GET.get('page'))

    all_territories = list(SHOP_TERRITORIES)

    return render(request, 'shops/shop_list.html', {
        'page_obj': page_obj,
        'total': qs.count(),
        'q': q, 'territories': territories,
        'all_territories': all_territories,
        'tip_top': tip_top, 'photos': photos,
        'taula_fridge': taula, 'talofa_voucher': talofa, 'faakau_com': faakau,
        'selected_types': ctypes, 'island': island, 'sort': sort, 'sales_year': sales_year,
        'islands': Shop.objects.values('island').annotate(n=Count('id')).order_by('island'),
        'sort_query': urlencode([(k, v) for k, vs in request.GET.lists() if k not in ('sort', 'page') for v in vs]),
        'customer_types': Shop.objects.values('customer_type').annotate(n=Count('id')).order_by('customer_type'),
    })


def shop_detail(request, shop_id):
    shop = get_object_or_404(Shop.objects.prefetch_related('photos'), id=shop_id)
    # Group photos by note for the detail view
    groups = {}
    for p in shop.photos.all():
        key = p.note.strip() if p.note.strip() else 'Unlabelled'
        groups.setdefault(key, []).append(p)

    sales = list(shop.monthly_sales.all()) if access.can_see_sales(request) else []   # newest month first
    this_year = date.today().year
    return render(request, 'shops/shop_detail.html', {
        'shop': shop,
        'photo_groups': groups,
        'sales': sales,
        'this_year': this_year,
        'year_total': sum(r.sales for r in sales if r.month.year == this_year),
        'last_12_total': sum(r.sales for r in sales[:12]),
        'chart_data': json.dumps([{'label': f'{r.month:%b %y}', 'value': float(r.sales)} for r in reversed(sales[:12])]),
    })


def _client_from_post(post, shop):
    """Fill a client from the add/edit form. Returns an error message or None."""
    shop.name           = post.get('name', '').strip()
    shop.customer_code  = post.get('customer_code', '').strip() or None
    shop.customer_type  = post.get('customer_type', '').strip()
    shop.contact_person = post.get('contact_person', '').strip() or None
    shop.phone          = post.get('phone', '').strip() or None
    shop.email          = post.get('email', '').strip().lower()
    shop.address        = post.get('address', '').strip() or None
    shop.island         = post.get('island', 'Upolu')
    shop.territory      = post.get('territory', '').strip().upper() or None
    shop.tip_top        = 'tip_top' in post
    shop.taula_fridge   = 'taula_fridge' in post
    shop.talofa_voucher = 'talofa_voucher' in post
    shop.faakau_com     = 'faakau_com' in post
    if not shop.name:
        return 'Client name is required'
    if shop.customer_code and Shop.objects.filter(customer_code__iexact=shop.customer_code).exclude(pk=shop.pk).exists():
        return f'Customer Code {shop.customer_code} is already used by another client'
    return None


def add_shop(request):
    if request.method == 'POST':
        shop = Shop()
        error = _client_from_post(request.POST, shop)
        if error:
            return render(request, 'shops/shop_form.html', {
                'error': error, 'action': 'Add', 'client': shop, 'territories': SHOP_TERRITORIES, 'customer_types': customer_type_choices(),
            })
        shop.save()
        # Handle photos with individual labels
        images = request.FILES.getlist('images')
        labels = request.POST.getlist('image_labels')
        for idx, img in enumerate(images):
            label = labels[idx] if idx < len(labels) else ''
            ShopPhoto.objects.create(shop=shop, image=img, note=label.strip())
        return redirect('shop_list')
    return render(request, 'shops/shop_form.html', {'action': 'Add', 'territories': SHOP_TERRITORIES,
                                                    'customer_types': customer_type_choices()})


def edit_shop(request, shop_id):
    shop = get_object_or_404(Shop.objects.prefetch_related('photos'), id=shop_id)
    if request.method == 'POST':
        if 'delete_shop' in request.POST:
            shop.delete()
            return redirect('shop_list')
        error = _client_from_post(request.POST, shop)
        if error:   # show the form again with what was typed
            return render(request, 'shops/shop_form.html', {
                'error': error, 'action': 'Edit', 'shop': shop, 'client': shop, 'territories': SHOP_TERRITORIES, 'customer_types': customer_type_choices(),
            })
        shop.save()
        # Delete removed photos
        for pid in request.POST.getlist('delete_photos'):
            try:
                p = ShopPhoto.objects.get(pk=pid, shop=shop)
                p.image.delete(save=False)
                p.delete()
            except ShopPhoto.DoesNotExist:
                pass
        # Update existing photo notes
        for p in shop.photos.all():
            new_note = request.POST.get(f'note_{p.pk}', p.note)
            if new_note != p.note:
                p.note = new_note
                p.save()
        # Add new photos with individual labels
        images = request.FILES.getlist('images')
        labels = request.POST.getlist('image_labels')
        for idx, img in enumerate(images):
            label = labels[idx] if idx < len(labels) else ''
            ShopPhoto.objects.create(shop=shop, image=img, note=label.strip())
        return redirect('shop_detail', shop_id=shop.id)
    return render(request, 'shops/shop_form.html', {'action': 'Edit', 'shop': shop, 'client': shop,
                                                    'territories': SHOP_TERRITORIES, 'customer_types': customer_type_choices()})


def delete_shop(request, shop_id):
    shop = get_object_or_404(Shop, id=shop_id)
    shop.delete()
    return redirect('shop_list')


def territory_shops(request, territory):
    qs = Shop.objects.prefetch_related('photos').filter(island='Upolu', territory=territory)
    q = request.GET.get('q', '')
    tt = request.GET.get('tip_top', '')
    if q:
        qs = qs.filter(name__icontains=q)
    if tt == '1':
        qs = qs.filter(tip_top=True)
    elif tt == '0':
        qs = qs.filter(tip_top=False)
    page_obj = Paginator(qs, 9).get_page(request.GET.get('page'))
    return render(request, 'shops/island_shops.html', {
        'page_obj': page_obj, 'territory': territory, 'island': 'Upolu'
    })


def upolu_shops(request, region):
    qs = Shop.objects.prefetch_related('photos').filter(island='Upolu')
    q = request.GET.get('q', '')
    tt = request.GET.get('tip_top', '')
    if q:
        qs = qs.filter(name__icontains=q)
    if tt == '1':
        qs = qs.filter(tip_top=True)
    elif tt == '0':
        qs = qs.filter(tip_top=False)
    page_obj = Paginator(qs, 9).get_page(request.GET.get('page'))
    return render(request, 'shops/island_shops.html', {
        'page_obj': page_obj, 'island': 'Upolu'
    })


def savaii_shops(request, region):
    qs = Shop.objects.prefetch_related('photos').filter(island='Savaii')
    q = request.GET.get('q', '')
    tt = request.GET.get('tip_top', '')
    if q:
        qs = qs.filter(name__icontains=q)
    if tt == '1':
        qs = qs.filter(tip_top=True)
    elif tt == '0':
        qs = qs.filter(tip_top=False)
    page_obj = Paginator(qs, 9).get_page(request.GET.get('page'))
    return render(request, 'shops/island_shops.html', {
        'page_obj': page_obj, 'island': 'Savaii'
    })


# ══════════════════════════════════════════════════════════════════════════════
# PROMOTIONS
# ══════════════════════════════════════════════════════════════════════════════

PROMOTION_LOGOS = {
    'Ah Liki Wholesale': 'imgs/ahliki_logo.png',
    'Farmer Joe':        'imgs/farmerjoe_logo.png',
    'Taula':             'imgs/taula_logo.png',
    'Burger Bills':      'imgs/burgerbills_logo.png',
    'INKPRO':            'imgs/inkpro_logo.png',
}


def _filtered_promotions(request):
    """Promotions matching the search/filter query string, shared by the page and its report."""
    qs = Promotion.objects.all()
    q       = request.GET.get('search_query', '').strip()
    company = request.GET.get('company', '')
    status  = request.GET.get('status', '')
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(details__icontains=q) |
                       Q(prizes__icontains=q) | Q(company__icontains=q))
    if company:
        qs = qs.filter(company=company)
    if status in dict(Promotion.STATUS_CHOICES):
        qs = qs.filter(Promotion.status_q(status))
    return qs, q, company, status


def _promotion_from_post(post, promo):
    """Fill a promotion from the add/edit form. Returns a list of error messages."""
    promo.name       = post.get('name', '').strip()
    promo.company    = post.get('company', '')
    promo.details    = post.get('details', '').strip()
    promo.prizes     = post.get('prizes', '').strip()
    errors = []
    for field in ('start_date', 'end_date'):
        value = post.get(field, '').strip()
        try:
            setattr(promo, field, date.fromisoformat(value) if value else None)
        except ValueError:
            errors.append('Dates must be valid, e.g. 2026-10-01.')
    if not promo.name:
        errors.append('Promotion name is required.')
    if promo.company not in dict(Promotion.COMPANY_CHOICES):
        errors.append('Choose a company.')
    if promo.start_date and promo.end_date and promo.end_date < promo.start_date:
        errors.append('End date can’t be before the start date.')
    return errors


@login_required(login_url='login')
def promotion_form(request, promo_id=None):
    promo = get_object_or_404(Promotion, pk=promo_id) if promo_id else Promotion()
    errors = []
    if request.method == 'POST':
        if promo.pk and 'delete_promotion' in request.POST:
            promo.delete()
            return redirect('promotion_list')
        errors = _promotion_from_post(request.POST, promo)
        if not errors:
            promo.save()
            return redirect('promotion_list')
    return render(request, 'shops/promotion_form.html', {
        'promo': promo, 'errors': errors,
        'action': 'Edit' if promo.pk else 'Add',
        'company_choices': Promotion.COMPANY_CHOICES,
    })


@login_required(login_url='login')
def promotion_list(request):
    promos, q, company, status = _filtered_promotions(request)
    promos = list(promos)
    companies = []
    for code, label in Promotion.COMPANY_CHOICES:
        if company and code != company:
            continue
        items = [p for p in promos if p.company == code]
        companies.append({
            'name': label,
            'logo': PROMOTION_LOGOS.get(code),
            'promotions': items,
            'active_count': sum(1 for p in items if p.status == 'Active'),
        })
    return render(request, 'shops/promotion_list.html', {
        'companies': companies,
        'total': len(promos),
        'active_total': sum(c['active_count'] for c in companies),
        'company_choices': Promotion.COMPANY_CHOICES,
        'status_choices': Promotion.STATUS_CHOICES,
        'search_query': q,
        'selected_company': company,
        'selected_status': status,
        'is_filtered': bool(q or company or status),
    })


# ══════════════════════════════════════════════════════════════════════════════
# HORECCA
# ══════════════════════════════════════════════════════════════════════════════

def _year_param(request):
    try:
        return int(request.GET.get('year') or date.today().year)
    except ValueError:
        return date.today().year


@login_required(login_url='login')
def corporate_sales(request):
    """Actual sales against target for each corporate account manager."""
    year = _year_param(request)
    everyone, unmatched = corporate.year_summary(year)
    # A rep sees only their own stream in full; the cards on top show everyone's % of this month's target
    own = corporate.own_rep_key(request.user)
    managers = [m for m in everyone if m['key'] == own] if own else everyone
    month_cards = [{'key': m['key'], 'name': m['name'], 'color': m['color'], 'streams': m['streams'],
                    'month_label': m['month_label'], 'month_pct': m['month_pct'], 'is_me': m['key'] == own}
                   for m in everyone]
    chart = [{'key': m['key'], 'name': m['name'], 'color': m['color'],
              'actual': [float(v) if v is not None else None for v in m['actual']],
              'previous': [float(v) if v is not None else None for v in m['previous']],
              'target': [float(v) if v is not None else None for v in m['target']],
              # Top 10 products: all the rep's clients, and each of their top clients (picked by clicking one)
              'products': {'all': corporate.top_products(m['client_ids'], year),
                           **{str(c['shop_id']): corporate.top_products([c['shop_id']], year) for c in m['top_clients']}}}
             for m in managers]
    # The All slide puts every stream together; a rep only sees their own stream, so they don't get it
    overall = None if own else corporate.combined_summary(everyone)
    return render(request, 'shops/corporate_sales.html', {
        'managers': managers, 'year': year, 'years': range(date.today().year + 1, date.today().year - 4, -1),
        'overall': overall, 'slide_offset': 1 if overall else 0,
        'chart_data': json.dumps({'labels': corporate.MONTH_LABELS, 'managers': chart, 'year': year,
                                  'all': {'actual': [float(v) if v is not None else None for v in overall['actual']],
                                          'previous': [float(v) if v is not None else None for v in overall['previous']],
                                          'target': [float(v) if v is not None else None for v in overall['target']]}
                                         if overall else None,
                                  # the month still in progress gets a lighter bar
                                  'currentMonth': date.today().month - 1 if year == date.today().year else -1}),
        'unmatched_types': [] if own else unmatched,
        'has_targets': any(v is not None for m in managers for v in m['target']),
        'month_cards': month_cards, 'own_rep': own,
        # when the sales figures last changed, so the team can see how current the page is
        'updated_as_of': MonthlySales.objects.aggregate(last=Max('updated_at'))['last'],
    })


@login_required(login_url='login')
def corporate_manager(request, manager):
    """One manager's clients and their sales, with search and filters. ?view=sales lists each monthly sale.
    manager='all' combines every corporate stream, with a filter for who looks after each client."""
    own = corporate.own_rep_key(request.user)
    if own and manager != own:
        if manager == 'all':
            return redirect(reverse('corporate_manager', args=[own]) + ('?' + request.GET.urlencode() if request.GET else ''))
        return access.deny(request, 'other reps’ clients')
    _, types_by_manager, _ = corporate.client_ids_by_manager()
    reps = corporate.managers()
    owner_of_type = {t: mm for mm in reps for t in types_by_manager[mm['key']]}
    f = {k: request.GET.get(k, '').strip() for k in ('q', 'type', 'territory', 'month', 'sales', 'sort', 'view', 'person')}
    if manager == 'all':
        m = {'key': 'all', 'name': 'Corporate Sales Clients', 'color': '#0F172A',
             'streams': [f"{mm['name']}: {', '.join(mm['streams'])}" for mm in reps]}
        people = [mm['key'] for mm in reps if f['person'] in ('', mm['key'])]
    else:
        m = next((mm for mm in reps if mm['key'] == manager), None)
        if m is None:
            raise Http404
        people = [manager]
    types = sorted(t for key in people for t in types_by_manager[key])
    clients = Shop.objects.filter(customer_type__in=types)

    year = _year_param(request)
    if f['q']:
        clients = clients.filter(Q(name__icontains=f['q']) | Q(customer_code__iexact=f['q']) |
                                 Q(contact_person__icontains=f['q']))
    if f['type'] in types:
        clients = clients.filter(customer_type=f['type'])
    if f['territory']:
        clients = clients.filter(territory=f['territory'])
    month = int(f['month']) if f['month'].isdigit() and 1 <= int(f['month']) <= 12 else None
    period = Q(month__year=year) & (Q(month__month=month) if month else Q())
    shop_period = Q(monthly_sales__month__year=year) & (Q(monthly_sales__month__month=month) if month else Q())
    period_label = f'{corporate.MONTH_LABELS[month - 1]} {year}' if month else str(year)

    clients = clients.annotate(period_sales=Sum('monthly_sales__sales', filter=shop_period))
    if f['sales'] == 'with':
        clients = clients.filter(period_sales__isnull=False)
    elif f['sales'] == 'without':
        clients = clients.filter(period_sales__isnull=True)
    order = {'name': ['name'], 'code': ['customer_code', 'name']}.get(f['sort'], [F('period_sales').desc(nulls_last=True), 'name'])
    clients = clients.order_by(*order)

    sales = (MonthlySales.objects.filter(period, shop__in=clients.values('id'))
             .select_related('shop').order_by('-month', '-sales'))
    total = sales.aggregate(t=Sum('sales'))['t'] or 0
    # Target vs sales for the same months only: months with a target that have already started
    targets = SalesTarget.objects.filter(period, manager__in=people)
    if year == date.today().year:
        targets = targets.filter(month__lte=date.today())
    target_months = [t.month for t in targets]
    target = sum(t.amount for t in targets) or None
    total_on_target = sales.filter(month__in=target_months).aggregate(t=Sum('sales'))['t'] or 0
    target_note = (f"Compared with sales in {corporate.month_span([d.month - 1 for d in target_months])} only"
                   if target and not month and len(target_months) < (date.today().month if year == date.today().year else 12)
                   else '')

    if request.GET.get('export'):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (f'attachment; filename="{manager}_{f["view"] or "clients"}_'
                                           f'{period_label.replace(" ", "_")}.csv"')
        response.write('\ufeff')
        w = csv.writer(response)
        if f['view'] == 'sales':
            w.writerow(['Customer Code', 'Customer Name', 'Customer Type', 'Looked After By', 'Month', 'Sales'])
            for r in sales:
                w.writerow([r.shop.customer_code or '', r.shop.name, r.shop.customer_type,
                            owner_of_type[r.shop.customer_type]['name'], f'{r.month:%Y-%m}', r.sales])
        else:
            w.writerow(['Customer Code', 'Name', 'Customer Type', 'Looked After By', 'Contact Person', 'Phone Number',
                        'Territory Code', 'Email', f'Sales {period_label}'])
            for c in clients:
                w.writerow([c.customer_code or '', c.name, c.customer_type, owner_of_type[c.customer_type]['name'],
                            c.contact_person or '', c.phone or '', c.territory or '', c.email,
                            c.period_sales if c.period_sales is not None else ''])
        return response

    rows = sales if f['view'] == 'sales' else clients
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    for row in page:   # who looks after each client, for the combined view
        row.owner = owner_of_type[(row.shop if f['view'] == 'sales' else row).customer_type]
    base = request.GET.copy()   # filters only; view and sort are added back once by each link
    for key in ('page', 'export', 'view', 'sort'):
        base.pop(key, None)
    params = base.copy()
    for key in ('view', 'sort'):
        if f[key]:
            params[key] = f[key]
    return render(request, 'shops/corporate_manager.html', {
        'm': m, 'types': types, 'f': f, 'combined': manager == 'all', 'managers': reps, 'year': year, 'month': month, 'period_label': period_label,
        'page_obj': page, 'client_total': clients.count(), 'with_sales': clients.filter(period_sales__isnull=False).count(),
        'total': total, 'target': target, 'target_note': target_note, 'own_rep': own,
        'pct': round(total_on_target / target * 100) if target else None,
        'territories': sorted(t for t in Shop.objects.filter(customer_type__in=types)
                              .values_list('territory', flat=True).distinct() if t),
        'years': range(date.today().year + 1, date.today().year - 4, -1),
        'month_choices': list(enumerate(corporate.MONTH_LABELS, start=1)),
        'query': params.urlencode(),
        'base_query': base.urlencode(),
    })


@login_required(login_url='login')
def corporate_targets(request):
    """Enter each manager's monthly targets for a year. A blank box removes that month's target."""
    if corporate.own_rep_key(request.user):
        return access.deny(request, 'setting targets')
    year = _year_param(request)
    errors = []
    reps = corporate.managers()
    if request.method == 'POST':
        with transaction.atomic():
            for m in reps:
                for i in range(12):
                    raw = request.POST.get(f"{m['key']}_{i + 1}", '').strip()
                    month = date(year, i + 1, 1)
                    if not raw:
                        SalesTarget.objects.filter(manager=m['key'], month=month).delete()
                        continue
                    try:
                        amount = client_import.parse_money(raw)
                    except (InvalidOperation, ValueError):
                        errors.append(f"{m['name']}, {corporate.MONTH_LABELS[i]}: “{raw}” is not a number")
                        continue
                    SalesTarget.objects.update_or_create(manager=m['key'], month=month, defaults={'amount': amount})
            if errors:
                transaction.set_rollback(True)
        if not errors:
            return redirect(f"{reverse('corporate_sales')}?year={year}")
    saved = {(t.manager, t.month.month): t.amount for t in SalesTarget.objects.filter(month__year=year)}
    # last year's sales per month, which the calculator grows by a percentage to suggest each target
    ids, _, _ = corporate.client_ids_by_manager()
    previous = {}
    for m in reps:
        for r in (MonthlySales.objects.filter(month__year=year - 1, shop_id__in=ids[m['key']])
                  .values('month').annotate(total=Sum('sales'))):
            previous[(m['key'], r['month'].month)] = r['total']
    rows = [{**m, 'cells': [{'name': f"{m['key']}_{i + 1}", 'label': corporate.MONTH_LABELS[i],
                             'value': request.POST.get(f"{m['key']}_{i + 1}") if errors else saved.get((m['key'], i + 1), ''),
                             'previous': previous.get((m['key'], i + 1))}
                            for i in range(12)]}
            for m in reps]
    return render(request, 'shops/corporate_targets.html', {
        'rows': rows, 'year': year, 'errors': errors, 'months': corporate.MONTH_LABELS,
        'has_previous': bool(previous),
    })


def business_list(request):
    qs = Business.objects.prefetch_related('photos').all()
    q      = request.GET.get('search_query', '').strip()
    island = request.GET.get('island', '')
    btype  = request.GET.get('business_type', '')
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(location__icontains=q))
    if island:
        qs = qs.filter(island=island)
    if btype:
        qs = qs.filter(business_type=btype)
    qs = qs.order_by('name')
    return render(request, 'shops/business_list.html', {
        'businesses': qs,
        'islands': Business.ISLAND_CHOICES,
        'business_types': Business.BUSINESS_TYPES,
        'selected_island': island,
        'selected_business_type': btype,
        'search_query': q,
    })


def add_business(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            return render(request, 'shops/business_form.html', {
                'error': 'Name is required', 'action': 'Add', 'form_data': request.POST
            })
        biz = Business.objects.create(
            name          = name,
            business_type = request.POST.get('business_type', 'HOTEL'),
            island        = request.POST.get('island', 'Upolu'),
            location      = request.POST.get('location', ''),
        )
        images = request.FILES.getlist('images')
        labels = request.POST.getlist('image_labels')
        for idx, img in enumerate(images):
            label = labels[idx] if idx < len(labels) else ''
            BusinessPhoto.objects.create(business=biz, image=img, note=label.strip())
        return redirect('business_list')
    return render(request, 'shops/business_form.html', {'action': 'Add'})


def edit_business(request, biz_id):
    biz = get_object_or_404(Business.objects.prefetch_related('photos'), id=biz_id)
    if request.method == 'POST':
        if 'delete_business' in request.POST:
            biz.delete()
            return redirect('business_list')
        biz.name          = request.POST.get('name', biz.name).strip() or biz.name
        biz.business_type = request.POST.get('business_type', biz.business_type)
        biz.island        = request.POST.get('island', biz.island)
        biz.location      = request.POST.get('location', biz.location)
        biz.save()
        for pid in request.POST.getlist('delete_photos'):
            try:
                p = BusinessPhoto.objects.get(pk=pid, business=biz)
                p.image.delete(save=False); p.delete()
            except BusinessPhoto.DoesNotExist:
                pass
        for p in biz.photos.all():
            new_note = request.POST.get(f'note_{p.pk}', p.note)
            if new_note != p.note:
                p.note = new_note; p.save()
        images = request.FILES.getlist('images')
        labels = request.POST.getlist('image_labels')
        for idx, img in enumerate(images):
            label = labels[idx] if idx < len(labels) else ''
            BusinessPhoto.objects.create(business=biz, image=img, note=label.strip())
        return redirect('business_list')
    return render(request, 'shops/business_form.html', {'action': 'Edit', 'biz': biz})


def delete_business(request, biz_id):
    biz = get_object_or_404(Business, id=biz_id)
    biz.delete()
    return redirect('business_list')


# ══════════════════════════════════════════════════════════════════════════════
# SPONSORSHIPS
# ══════════════════════════════════════════════════════════════════════════════

def sponsorship_list(request):
    qs = Sponsorship.objects.prefetch_related('photos').all()
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    total_val   = float(qs.aggregate(v=Sum('value'))['v'] or 0)
    active      = qs.filter(status='Active')
    active_val  = float(active.aggregate(v=Sum('value'))['v'] or 0)
    all_customers = sorted(set(
        list(Shop.objects.values_list('name', flat=True)) +
        list(Business.objects.values_list('name', flat=True))
    ))
    return render(request, 'shops/sponsorship_list.html', {
        'sponsorships': qs,
        'total_val': total_val,
        'active_count': active.count(),
        'active_val': active_val,
        'selected_status': status,
        'all_customers': all_customers,
    })


def add_sponsorship(request):
    all_customers = sorted(set(
        list(Shop.objects.values_list('name', flat=True)) +
        list(Business.objects.values_list('name', flat=True))
    ))
    if request.method == 'POST':
        customer = request.POST.get('customer', '').strip()
        value    = request.POST.get('value', '')
        if not customer or not value:
            return render(request, 'shops/sponsorship_form.html', {
                'error': 'Customer and value are required',
                'action': 'Add', 'form_data': request.POST,
                'all_customers': all_customers,
            })
        sp = Sponsorship.objects.create(
            customer = customer,
            type     = request.POST.get('type', 'Signage'),
            sponsorship_type = request.POST.get('sponsorship_type', 'Cash Value'),
            value    = float(value),
            status   = request.POST.get('status', 'Active'),
            start    = request.POST.get('start') or None,
            end      = request.POST.get('end')   or None,
            notes    = request.POST.get('notes', ''),
        )
        images = request.FILES.getlist('images')
        labels = request.POST.getlist('image_labels')
        for idx, img in enumerate(images):
            label = labels[idx] if idx < len(labels) else ''
            SponsorshipPhoto.objects.create(sponsorship=sp, image=img, note=label.strip())
        return redirect('sponsorship_list')
    return render(request, 'shops/sponsorship_form.html', {
        'action': 'Add', 'all_customers': all_customers,
        'sp_types': ['Signage','Cooler','Event','Vehicle','Uniform','Digital','Other'],
        'sponsorship_types': Sponsorship.SPONSORSHIP_TYPE_CHOICES,
    })


def edit_sponsorship(request, sp_id):
    sp = get_object_or_404(Sponsorship.objects.prefetch_related('photos'), id=sp_id)
    all_customers = sorted(set(
        list(Shop.objects.values_list('name', flat=True)) +
        list(Business.objects.values_list('name', flat=True))
    ))
    if request.method == 'POST':
        if 'delete_sponsorship' in request.POST:
            sp.delete()
            return redirect('sponsorship_list')
        sp.customer = request.POST.get('customer', sp.customer)
        sp.type     = request.POST.get('type',     sp.type)
        sp.sponsorship_type = request.POST.get('sponsorship_type', sp.sponsorship_type)
        sp.value    = float(request.POST.get('value', sp.value))
        sp.status   = request.POST.get('status',   sp.status)
        sp.start    = request.POST.get('start')    or sp.start
        sp.end      = request.POST.get('end')      or sp.end
        sp.notes    = request.POST.get('notes',    sp.notes)
        sp.save()
        for pid in request.POST.getlist('delete_photos'):
            try:
                p = SponsorshipPhoto.objects.get(pk=pid, sponsorship=sp)
                p.image.delete(save=False); p.delete()
            except SponsorshipPhoto.DoesNotExist:
                pass
        for p in sp.photos.all():
            new_note = request.POST.get(f'note_{p.pk}', p.note)
            if new_note != p.note:
                p.note = new_note; p.save()
        images = request.FILES.getlist('images')
        labels = request.POST.getlist('image_labels')
        for idx, img in enumerate(images):
            label = labels[idx] if idx < len(labels) else ''
            SponsorshipPhoto.objects.create(sponsorship=sp, image=img, note=label.strip())
        return redirect('sponsorship_list')
    return render(request, 'shops/sponsorship_form.html', {
        'action': 'Edit', 'sp': sp, 'all_customers': all_customers,
        'sp_types': ['Signage','Cooler','Event','Vehicle','Uniform','Digital','Other'],
        'sponsorship_types': Sponsorship.SPONSORSHIP_TYPE_CHOICES,
    })


def delete_sponsorship(request, sp_id):
    sp = get_object_or_404(Sponsorship, id=sp_id)
    sp.delete()
    return redirect('sponsorship_list')


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS / CSV DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def reports(request):
    from fe_orders.models import Order, Product
    shops = Shop.objects.all()
    sponsorships = Sponsorship.objects.all()
    sales_years = [d.year for d in MonthlySales.objects.dates('month', 'year', order='DESC')] or [date.today().year]
    latest = MonthlySales.objects.order_by('-month').values_list('month', flat=True).first()
    return render(request, 'shops/reports.html', {
        'client_count': shops.count(),
        'customer_types': shops.exclude(customer_type='').values_list('customer_type', flat=True).distinct().order_by('customer_type'),
        'territories': shops.exclude(territory__isnull=True).exclude(territory='')
                            .values_list('territory', flat=True).distinct().order_by('territory'),
        'sales_rows': MonthlySales.objects.count(),
        'sales_years': sales_years,
        'latest_month': latest,
        'month_choices': list(enumerate(corporate.MONTH_LABELS, start=1)),
        'managers': corporate.managers(),
        'order_count': Order.objects.count(),
        'product_count': Product.objects.count(),
        'today': date.today(),
        'promotion_count': Promotion.objects.count(),
        'company_choices': Promotion.COMPANY_CHOICES,
        'promotion_statuses': Promotion.STATUS_CHOICES,
        'businesses': Business.objects.count(),
        'business_types': Business.BUSINESS_TYPES,
        'sponsorship_count': sponsorships.count(),
        'sponsorship_summary': sponsorships.values('status').annotate(n=Count('id'), total=Sum('value')).order_by('status'),
    })


def _csv_response(name):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{name}_{date.today()}.csv"'
    response.write('\ufeff')   # so Excel opens names like Fa’atoaga correctly
    return response, csv.writer(response)


@login_required(login_url='login')
def download_report(request):
    report_type = request.GET.get('type', 'shops')
    island      = request.GET.get('island', '')
    status      = request.GET.get('status', '')
    ctype       = request.GET.get('customer_type', '')
    territory   = request.GET.get('territory', '')

    if report_type == 'shops':
        qs = Shop.objects.annotate(photo_count=Count('photos')).order_by('name')
        if island: qs = qs.filter(island=island)
        if territory: qs = qs.filter(territory=territory)
        if ctype == '__none__': qs = qs.filter(customer_type='')
        elif ctype: qs = qs.filter(customer_type=ctype)
        response, w = _csv_response('clients_report')
        w.writerow(['Customer Code', 'Name', 'Customer Type', 'Contact Person', 'Address', 'Island', 'Phone Number',
                    'Territory Code', 'Email', 'Tip Top', 'Taula Fridge', 'Talofa Voucher', 'Faakau.com', 'Photo Count', 'Created'])
        for s in qs:
            w.writerow([s.customer_code or '', s.name, s.customer_type, s.contact_person or '', s.address or '', s.island,
                        s.phone or '', s.territory or '', s.email,
                        'Yes' if s.tip_top else 'No', 'Yes' if s.taula_fridge else 'No', 'Yes' if s.talofa_voucher else 'No', 'Yes' if s.faakau_com else 'No',
                        s.photo_count, s.created or ''])
        return response

    if report_type == 'monthly_sales':
        return _monthly_sales_report(request)

    if report_type == 'corporate':
        return _corporate_report(request)

    response = HttpResponse(content_type='text/csv')

    if report_type == 'horecca':
        qs = Business.objects.prefetch_related('photos').all()
        if island: qs = qs.filter(island=island)
        if request.GET.get('business_type'): qs = qs.filter(business_type=request.GET['business_type'])
        response['Content-Disposition'] = f'attachment; filename="horecca_report_{date.today()}.csv"'
        w = csv.writer(response)
        w.writerow(['ID', 'Name', 'Type', 'Island', 'Location', 'Photo Count', 'Created'])
        for b in qs:
            w.writerow([b.pk, b.name, b.business_type, b.island, b.location,
                        b.photos.count(), b.created_at.date()])

    elif report_type == 'promotions':
        qs, *_ = _filtered_promotions(request)
        qs = qs.order_by('company', '-start_date', 'name')
        response['Content-Disposition'] = f'attachment; filename="promotions_report_{date.today()}.csv"'
        w = csv.writer(response)
        w.writerow(['ID', 'Promotion Name', 'Company', 'Details', 'Prizes', 'Start Date', 'End Date', 'Status', 'Created'])
        for p in qs:
            w.writerow([p.pk, p.name, p.company, p.details, p.prizes,
                        p.start_date or '', p.end_date or '', p.status, p.created_at.date()])

    else:  # sponsorships
        qs = Sponsorship.objects.prefetch_related('photos').all()
        if status: qs = qs.filter(status=status)
        response['Content-Disposition'] = f'attachment; filename="sponsorships_report_{date.today()}.csv"'
        w = csv.writer(response)
        w.writerow(['ID', 'Customer', 'Type', 'Sponsorship Type', 'Value (WST)', 'Status', 'Start', 'End', 'Notes', 'Photo Count', 'Created'])
        for s in qs:
            w.writerow([s.pk, s.customer, s.type, s.sponsorship_type, s.value, s.status,
                        s.start or '', s.end or '', s.notes, s.photos.count(), s.created])

    return response


def _monthly_sales_report(request):
    """Monthly sales in three layouts: one row per client per month, one total per client, or months as columns."""
    year = _year_param(request)
    month = request.GET.get('month', '')
    month = int(month) if month.isdigit() and 1 <= int(month) <= 12 else None
    layout = request.GET.get('layout', 'rows')
    ctype = request.GET.get('customer_type', '')
    person = request.GET.get('person', '')

    _, types, _ = corporate.client_ids_by_manager()
    owner = {t: m['name'] for m in corporate.managers() for t in types[m['key']]}

    qs = MonthlySales.objects.filter(month__year=year).select_related('shop')
    if month:
        qs = qs.filter(month__month=month)
    if ctype:
        qs = qs.filter(shop__customer_type=ctype)
    if person == 'corporate':
        qs = qs.filter(shop__customer_type__in=list(owner))
    elif person in types:
        qs = qs.filter(shop__customer_type__in=types[person])
    label = f'{year}-{month:02d}' if month else str(year)
    response, w = _csv_response(f'monthly_sales_{label}' + (f'_{person}' if person else ''))

    if layout == 'clients':
        w.writerow(['Customer Code', 'Customer Name', 'Customer Type', 'Corporate Manager', 'Territory Code',
                    f'Total Sales {label}', 'Months With Sales'])
        rows = (qs.values('shop__customer_code', 'shop__name', 'shop__customer_type', 'shop__territory')
                .annotate(total=Sum('sales'), months=Count('id')).order_by('-total'))
        for r in rows:
            w.writerow([r['shop__customer_code'] or '', r['shop__name'], r['shop__customer_type'],
                        owner.get(r['shop__customer_type'], ''), r['shop__territory'] or '', f"{r['total']:.2f}", r['months']])
    elif layout == 'pivot':
        months = [m for m in range(1, 13) if not month or m == month]
        w.writerow(['Customer Code', 'Customer Name', 'Customer Type', 'Corporate Manager']
                   + [f'{corporate.MONTH_LABELS[m - 1]} {year}' for m in months] + ['Total'])
        table = {}
        for r in qs.order_by('shop__name'):
            row = table.setdefault(r.shop_id, {'shop': r.shop, 'months': {}})
            row['months'][r.month.month] = r.sales
        for row in sorted(table.values(), key=lambda x: -sum(x['months'].values())):
            shop = row['shop']
            w.writerow([shop.customer_code or '', shop.name, shop.customer_type, owner.get(shop.customer_type, '')]
                       + [row['months'].get(m, '') for m in months] + [f"{sum(row['months'].values()):.2f}"])
    else:
        w.writerow(['Customer Code', 'Customer Name', 'Customer Type', 'Corporate Manager', 'Month', 'Sales'])
        for r in qs.order_by('month', 'shop__name'):
            w.writerow([r.shop.customer_code or '', r.shop.name, r.shop.customer_type,
                        owner.get(r.shop.customer_type, ''), f'{r.month:%Y-%m}', r.sales])
    return response


def _corporate_report(request):
    """Actual against target per corporate manager per month."""
    year = _year_param(request)
    person = request.GET.get('person', '')
    managers, _ = corporate.year_summary(year)
    response, w = _csv_response(f'corporate_sales_{year}' + (f'_{person}' if person else ''))
    w.writerow(['Manager', 'Streams', 'Month', 'Actual Sales', 'Target', 'Variance', '% of Target'])
    for m in managers:
        if person and m['key'] != person:
            continue
        for i, label in enumerate(corporate.MONTH_LABELS):
            actual, target = m['actual'][i] or 0, m['target'][i]
            w.writerow([m['name'], ', '.join(m['streams']), f'{label} {year}', f'{actual:.2f}',
                        '' if target is None else f'{target:.2f}',
                        '' if target is None else f'{actual - target:.2f}',
                        f'{round(actual / target * 100)}%' if target else ''])
        total_target = sum(v or 0 for v in m['target'])
        w.writerow([m['name'], 'TOTAL', str(year), f"{sum(v or 0 for v in m['actual']):.2f}",
                    f'{total_target:.2f}' if total_target else '', '', ''])
    return response


# ══════════════════════════════════════════════════════════════════════════════
# CSV IMPORT
# ══════════════════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def monthly_sales_list(request):
    """Monthly sales per client, filtered by month and search; ?export=1 downloads the same rows as CSV."""
    months = list(MonthlySales.objects.dates('month', 'month', order='DESC'))
    month = request.GET.get('month') or (f'{months[0]:%Y-%m}' if months else '')
    q = request.GET.get('q', '').strip()
    qs = MonthlySales.objects.select_related('shop').order_by('-month', '-sales')
    if month != 'all' and month:
        try:
            qs = qs.filter(month=client_import.parse_month(month))
        except ValueError:
            month = ''
    if q:
        qs = qs.filter(Q(shop__name__icontains=q) | Q(shop__customer_code__iexact=q))

    if request.GET.get('export'):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="monthly_sales_{month or "all"}.csv"'
        response.write('\ufeff')
        w = csv.writer(response)
        w.writerow([h for _, h in client_import.SALES_COLUMNS])
        for r in qs:
            w.writerow([r.shop.customer_code or '', r.shop.name, f'{r.month:%Y-%m}', r.sales])
        return response

    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    return render(request, 'shops/monthly_sales.html', {
        'page_obj': page, 'months': months, 'month': month, 'q': q,
        'total': qs.aggregate(t=Sum('sales'))['t'] or 0, 'count': qs.count(),
    })


def _num(v):
    return float(v) if v is not None else None


@login_required(login_url='login')
def product_sales_page(request):
    """Product sales dashboard: search, filters, charts on the left, pinned quick links on the right, table below."""
    f = product_sales.read_filters(request.GET)
    page = Paginator(product_sales.table(f), 50).get_page(request.GET.get('page'))
    base = request.GET.copy()
    for key in ('page', 'sort', 'partial'):
        base.pop(key, None)
    table_total = product_sales.dated(product_sales.product_scope(f), f).count() if f['tq'] else None
    # filters kept when jumping to a quick link (which picks one product and clears the search)
    keep_query = urlencode({k: request.GET[k] for k in ('year', 'compare', 'from', 'to', 'category', 'lm') if request.GET.get(k)})
    # where ☆ pin buttons come back to: this page, never the live-search fragment
    page_url = request.path + '?' + urlencode([(k, v) for k, vs in request.GET.lists() if k != 'partial' for v in vs])
    pinned = set(PinnedProduct.objects.values_list('product_code', flat=True))
    if request.GET.get('partial') == 'table':   # live table search: just the rows, no charts
        return render(request, 'shops/_ps_table.html', {
            'f': f, 'page_obj': page, 'row_count': page.paginator.count, 'table_total': table_total,
            'base_query': base.urlencode(), 'keep_query': keep_query, 'page_url': page_url, 'pinned': pinned,
        })
    a = product_sales.analytics(f)
    selected_name = (ProductSales.objects.filter(product_code__iexact=f['product'])
                     .order_by('-month').values_list('product_name', flat=True).first() if f['product'] else '')
    chart = {
        'trend': {'labels': a['trend']['labels'], 'values': [_num(v) for v in a['trend']['values']]},
        'yoy': {'labels': a['yoy']['labels'], 'year': f['year'], 'compare': f['compare'],
                'this': [_num(v) for v in a['yoy']['this']], 'last': [_num(v) for v in a['yoy']['last']]},
        'cumulative': {'this': [_num(v) for v in a['cumulative']['this']], 'last': [_num(v) for v in a['cumulative']['last']]},
        'top': {'labels': [r['name'] for r in a['top']['rows']], 'codes': [r['product_code'] for r in a['top']['rows']],
                'values': [_num(r['total']) for r in a['top']['rows']]},
    }
    month_i = f['link_month']   # the month the quick-link colours are judged on: picked, or the current month
    groups = product_sales.group_links(f['year'], f['compare'], month_i)
    links = product_sales.quick_links(f['year'], f['compare'], month_i)
    quick = product_sales.sort_quick_links(groups, links)
    # the search box finds groups too: offer any whose name matches
    matching_groups = [g for g in groups if f['q'] and f['q'].lower() in g['name'].lower()] if not f['group'] else []
    return render(request, 'shops/product_sales.html', {
        'f': f, 'kpi': a['kpi'], 'top_label': a['top']['label'], 'chart_data': json.dumps(chart),
        'links': links,
        'groups': groups, 'matching_groups': matching_groups,
        'quick': quick,
        'status_counts': {k: sum(1 for q in quick if q['status'] == k) for k in ('good', 'close', 'behind')},
        'link_month': f"{product_sales.MONTHS[month_i]} {f['year']}" if month_i >= 0 else '',
        'target_month': f"{product_sales.MONTHS[month_i]} {f['compare']}" if month_i >= 0 else '',
        'close_pct': product_sales.CLOSE_PCT,
        'link_month_i': month_i + 1, 'link_month_choices': list(enumerate(product_sales.MONTHS, start=1)),
        'link_month_uploaded': month_i >= 0 and ProductSales.objects.filter(month__year=f['year'], month__month=month_i + 1).exists(),
        # the month picker keeps every other filter and starts again at page 1
        'link_month_keep': [(k, v) for k, values in request.GET.lists() if k not in ('lm', 'page', 'partial') for v in values],
        'pinned': pinned, 'page_url': page_url,
        'page_obj': page, 'base_query': base.urlencode(), 'query': request.GET.urlencode(),
        # everything except the table search and page, kept as hidden fields in the table's search form
        'table_keep': [(k, v) for k, values in request.GET.lists() if k not in ('tq', 'page') for v in values],
        'clear_table_query': urlencode([(k, v) for k, values in request.GET.lists() if k not in ('tq', 'page') for v in values]),
        'table_total': table_total,
        'categories': product_sales.categories(), 'selected_name': selected_name,
        'row_count': page.paginator.count, 'filters_text': product_sales.describe(f),
        'has_data': ProductSales.objects.exists(),
        'all_products': ProductSales.objects.values('product_code').distinct().count(),
        'keep_query': keep_query,
    })


@login_required(login_url='login')
def product_group_form(request, group_id=None):
    """Add or edit a product group. "Preview" shows which products it would hold without saving."""
    group = get_object_or_404(ProductGroup, pk=group_id) if group_id else ProductGroup(
        name=request.GET.get('name', '').strip()[:100], keywords=request.GET.get('keywords', '').strip()[:255])
    errors = []
    if request.method == 'POST':
        if group.pk and 'delete' in request.POST:
            group.delete()
            return redirect('product_sales')
        group.name = request.POST.get('name', '').strip()[:100]
        group.keywords = ', '.join(k.strip() for k in request.POST.get('keywords', '').split(',') if k.strip())[:255]
        def codes(field):   # unique codes, in the order given
            return list(dict.fromkeys(c for c in re.split(r'[\s,;]+', request.POST.get(field, '')) if c))
        group.product_codes = '\n'.join(codes('product_codes'))
        group.exclude_codes = '\n'.join(codes('exclude_codes'))
        if not group.name:
            errors.append('Give the group a name, e.g. Tip Top.')
        elif ProductGroup.objects.filter(name__iexact=group.name).exclude(pk=group.pk).exists():
            errors.append(f'There’s already a group called “{group.name}”.')
        if not group.keyword_list() and not group.code_list():
            errors.append('Add at least one keyword or product code.')
        if not errors and 'preview' not in request.POST:
            group.save()
            return redirect(f"{reverse('product_sales')}?group={group.pk}")
    members = product_sales.group_members(group) if (group.keyword_list() or group.code_list()) else []
    unknown = [c for c in group.code_list() if not ProductSales.objects.filter(product_code=c).exists()]
    # every product, for the picker (searching and ticking happen in the browser)
    catalogue = [[r['product_code'], r['name'], float(r['total'])] for r in
                 ProductSales.objects.values('product_code').annotate(name=Max('product_name'), total=Sum('total_sales'))
                 .order_by('-total')]
    return render(request, 'shops/product_group_form.html', {
        'group': group, 'errors': errors, 'members': members[:200], 'member_count': len(members), 'unknown_codes': unknown,
        'catalogue': catalogue,
        'picked': group.code_list(), 'excluded': group.exclude_list(),
    })


@login_required(login_url='login')
def quick_link_targets(request):
    """Set monthly targets by hand for groups and pinned products. A blank box uses the same month last year."""
    year = product_sales.read_filters(request.GET)['year']
    errors = []
    if request.method == 'POST':
        groups = {f'g{g.id}': g for g in ProductGroup.objects.all()}
        codes = set(PinnedProduct.objects.values_list('product_code', flat=True))
        with transaction.atomic():
            for row in product_sales.target_grid(year):
                for i, cell in enumerate(row['cells']):
                    prefix = cell['name'].rsplit('_', 1)[0]
                    who = ({'group': groups[prefix]} if row['kind'] == 'group' else {'product_code': prefix[1:]})
                    if row['kind'] == 'product' and prefix[1:] not in codes:
                        continue
                    month = date(year, i + 1, 1)
                    raw = request.POST.get(cell['name'], '').strip()
                    if not raw:
                        QuickLinkTarget.objects.filter(month=month, **who).delete()
                        continue
                    try:
                        amount = client_import.parse_money(raw)
                    except (InvalidOperation, ValueError):
                        errors.append(f"{row['label']}, {cell['label']}: “{raw}” is not a number")
                        continue
                    QuickLinkTarget.objects.update_or_create(month=month, **who, defaults={'amount': amount})
            if errors:
                transaction.set_rollback(True)
        if not errors:
            messages.success(request, f'Quick-link targets for {year} saved.')
            return redirect(f"{reverse('product_sales')}?year={year}")
    rows = product_sales.target_grid(year)
    if errors:   # show what was typed so it can be fixed
        for row in rows:
            for cell in row['cells']:
                cell['value'] = request.POST.get(cell['name'], '')
    return render(request, 'shops/quick_link_targets.html', {
        'rows': rows, 'year': year, 'errors': errors, 'months': product_sales.MONTHS,
        'years': product_sales.read_filters({})['years'],
    })


@login_required(login_url='login')
@require_POST
def product_sales_pin(request):
    """Pin or unpin a product in the quick links."""
    code = request.POST.get('code', '').strip()
    if code:
        pin = PinnedProduct.objects.filter(product_code=code).first()
        if pin:
            pin.delete()
        elif ProductSales.objects.filter(product_code=code).exists():
            PinnedProduct.objects.create(product_code=code)
    nxt = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        nxt = reverse('product_sales')   # only ever go back to a page on this site
    return redirect(nxt)


@login_required(login_url='login')
def product_sales_export(request):
    """Excel workbook (whole report or one chart's sheet), or the table as CSV. Follows the page's filters."""
    f = product_sales.read_filters(request.GET)
    stamp = date.today().isoformat()
    if request.GET.get('format') == 'csv':
        response, w = _csv_response('product_sales')
        w.writerow([h for _, h in product_sales.COLUMNS])
        for r in product_sales.table(f).iterator():
            w.writerow([r.product_code, r.product_name, f'{r.month:%y-%m}', r.total_sales])
        return response
    sheet = request.GET.get('sheet') or None
    if sheet not in (None, 'summary', 'trend', 'yoy', 'cumulative', 'top', 'data'):
        sheet = None
    response = HttpResponse(product_sales.workbook(f, only=sheet),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    name = f'product_sales_{sheet or "report"}_{stamp}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{name}"'
    return response


@login_required(login_url='login')
def import_product_sales(request):
    """Upload monthly product sales. Re-uploading a product's month replaces its total."""
    return _run_upload(request, product_sales.import_product_sales, 'shops/import_product_sales.html',
                       {'columns': product_sales.COLUMNS})


def download_product_sales_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="product_sales_template.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in product_sales.COLUMNS])
    w.writerow(['AL10002999', 'Tip Top Banana Split 16L', '26-09', '45210.50'])
    w.writerow(['AL10002999', 'Tip Top Banana Split 16L', '26-08', '39875.00'])
    return response


@login_required(login_url='login')
def import_customer_product_sales(request):
    """Upload each client's sales per product per month, for the Top 10 products chart on Corporate Sales."""
    return _run_upload(request, product_sales.import_customer_product_sales, 'shops/import_customer_product_sales.html',
                       {'columns': product_sales.CUSTOMER_COLUMNS})


@login_required(login_url='login')
def download_customer_product_sales_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customer_product_sales_template.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in product_sales.CUSTOMER_COLUMNS])
    w.writerow(['C10023', 'Ministry of Health', 'AL10002999', 'Tip Top Banana Split 16L', '26-09', '1250.00'])
    w.writerow(['C10023', 'Ministry of Health', 'AL10001234', 'Anchor Milk Powder 1kg', '26-09', '860.50'])
    return response


def _run_upload(request, importer, template, extra):
    """Shared handling for the client and monthly sales CSV uploads."""
    result = None
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            result = importer(request.FILES['csv_file'])
        except client_import.ImportFileError as exc:
            return render(request, template, {**extra, 'error': str(exc)})
    return render(request, template, {**extra, 'result': result})


@login_required(login_url='login')
def import_shops(request):
    """Upload clients. Matches on Customer Code; see shops/client_import.py for the rules."""
    return _run_upload(request, client_import.import_clients, 'shops/import_shops.html',
                       {'columns': client_import.CLIENT_COLUMNS})


@login_required(login_url='login')
def import_monthly_sales(request):
    """Upload monthly sales totals per client. Re-uploading a month replaces its total."""
    return _run_upload(request, client_import.import_monthly_sales, 'shops/import_monthly_sales.html',
                       {'columns': client_import.SALES_COLUMNS})


@login_required(login_url='login')
def import_businesses(request):
    """Import HORECA businesses from CSV file."""
    if request.method == 'POST':
        form = BusinessCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                # Read and parse CSV
                dataset = Dataset().load(csv_file.read().decode('utf-8'), 'csv')
                resource = BusinessResource()
                result = resource.import_data(dataset, dry_run=False)

                error_list = []
                if result.has_errors():
                    for error in result.errors:
                        error_list.append(str(error))

                messages = {
                    'success': f'Successfully imported {result.total_rows} businesses.',
                    'errors': error_list,
                    'import_count': result.total_rows,
                }
                return render(request, 'shops/import_result.html', {
                    'model_type': 'HORECA Businesses',
                    'messages': messages,
                    'success': not result.has_errors(),
                })
            except Exception as e:
                return render(request, 'shops/import_businesses.html', {
                    'form': form,
                    'error': f'Error processing file: {str(e)}'
                })
    else:
        form = BusinessCSVImportForm()

    return render(request, 'shops/import_businesses.html', {'form': form})


@login_required(login_url='login')
def import_sponsorships(request):
    """Upload sponsorships. Matches on Customer + Type + Start Date; see shops/sponsorship_import.py for the rules."""
    return _run_upload(request, sponsorship_import.import_sponsorships, 'shops/import_sponsorships.html',
                       {'columns': sponsorship_import.COLUMNS})


def download_sales_template(request):
    """Download CSV template for monthly sales."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="monthly_sales_template.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in client_import.SALES_COLUMNS])
    w.writerow(['C00123', 'Example Store', '2026-09', '12500.00'])
    w.writerow(['C00123', 'Example Store', '2026-08', '11875.50'])
    return response


def download_shop_template(request):
    """Download CSV template for clients."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="clients_template.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in client_import.CLIENT_COLUMNS])
    w.writerow(['C00123', 'Example Store', 'Retail', 'Sione Tavita', 'Lalovaea', 'Upolu', '7771234', 'EC2',
                'store@example.com'])
    return response


def download_business_template(request):
    """Download CSV template for HORECA businesses."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="horecca_template.csv"'
    w = csv.writer(response)
    w.writerow(['name', 'business_type', 'island', 'location'])
    w.writerow(['Example Hotel', 'HOTEL', 'Upolu', 'Apia'])
    return response


def download_sponsorship_template(request):
    """Download CSV template for sponsorships."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sponsorship_template.csv"'
    w = csv.writer(response)
    w.writerow([h for _, h in sponsorship_import.COLUMNS])
    w.writerow(['Example Store', 'Signage', 'Cash Value', '5000.00', 'Active', '2026-01-01', '2026-12-31',
                'Shop front sign, annual'])
    w.writerow(['Example Hotel', 'Cooler', 'In-Kind Value', '1800.00', 'Pending', '2026-11-01', '',
                'Two-door cooler on loan'])
    return response


SURVEY_CSV_COLUMNS = ['Products', 'Customer/Shop', 'Period', 'Price', 'QTY', 'Location', 'Region']
SURVEY_CSV_EXAMPLES = [
    ['COKE CAN 330ml', '24/7 SAVALALO', 'May-26', '3.00', '100', 'SAVALALO', 'REGION 2'],
    ['Coca Cola 1.5L', 'Samoa Store', 'May-26', '6.50', '24', 'VAITELE', 'REGION 1'],
]
# CSV header (lowercased) → SurveyResponse field
SURVEY_CSV_FIELDS = {'products': 'product', 'customer/shop': 'customer', 'period': 'period', 'price': 'price',
                     'qty': 'quantity', 'location': 'location', 'region': 'region'}


def download_survey_template(request):
    """Download CSV template for survey responses."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="survey_responses_template.csv"'
    w = csv.writer(response)
    w.writerow(SURVEY_CSV_COLUMNS)
    w.writerows(SURVEY_CSV_EXAMPLES)
    return response


# ══════════════════════════════════════════════════════════════════════════════
# SURVEYS
# ══════════════════════════════════════════════════════════════════════════════

def survey_list(request):
    """List all surveys with pagination and filtering."""
    from .forms import SurveyForm
    
    qs = Survey.objects.prefetch_related('responses').all()
    category = request.GET.get('category', '')
    q = request.GET.get('search_query', '').strip()
    
    if category:
        qs = qs.filter(category=category)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(location__icontains=q) | Q(region__icontains=q))
    
    qs = qs.order_by('-created_at')
    page_obj = Paginator(qs, 10).get_page(request.GET.get('page'))
    
    return render(request, 'shops/survey_list.html', {
        'page_obj': page_obj,
        'categories': Survey.CATEGORY_CHOICES,
        'selected_category': category,
        'search_query': q,
    })


def add_survey(request):
    """Create a new survey."""
    from .forms import SurveyForm
    
    if request.method == 'POST':
        form = SurveyForm(request.POST)
        if form.is_valid():
            survey = form.save(commit=False)
            # Auto-fill created_by with current user's username
            if request.user.is_authenticated:
                survey.created_by = request.user.username
            else:
                survey.created_by = 'Anonymous'
            survey.save()
            return redirect('survey_detail', survey_id=survey.id)
    else:
        form = SurveyForm()
    
    return render(request, 'shops/survey_form.html', {'form': form, 'action': 'Create'})


def survey_detail(request, survey_id):
    """View survey details, responses, and analysis."""
    survey = get_object_or_404(Survey.objects.prefetch_related('responses'), id=survey_id)
    responses = survey.responses.all().order_by('-recorded_at')
    page_obj = Paginator(responses, 20).get_page(request.GET.get('page'))
    
    # Prepare analysis data
    analysis_data = {
        'total_responses': survey.response_count,
        'locations': list(set([r.location for r in survey.responses.all() if r.location])),
        'regions': list(set([r.region for r in survey.responses.all() if r.region])),
        'avg_price': survey.responses.filter(price__isnull=False).aggregate(Avg('price'))['price__avg'],
    }
    
    return render(request, 'shops/survey_detail.html', {
        'survey': survey,
        'page_obj': page_obj,
        'analysis_data': analysis_data,
    })


def edit_survey(request, survey_id):
    """Edit survey details."""
    from .forms import SurveyForm
    
    survey = get_object_or_404(Survey, id=survey_id)
    if request.method == 'POST':
        form = SurveyForm(request.POST, instance=survey)
        if form.is_valid():
            survey = form.save(commit=False)
            # Auto-fill created_by with current user's username on edit
            if request.user.is_authenticated:
                survey.created_by = request.user.username
            survey.save()
            return redirect('survey_detail', survey_id=survey.id)
    else:
        form = SurveyForm(instance=survey)
    
    return render(request, 'shops/survey_form.html', {'form': form, 'action': 'Edit', 'survey': survey})


def delete_survey(request, survey_id):
    """Delete a survey and all its responses."""
    survey = get_object_or_404(Survey, id=survey_id)
    if request.method == 'POST':
        survey.delete()
        return redirect('survey_list')
    return render(request, 'shops/survey_confirm_delete.html', {'survey': survey})


def add_survey_response(request, survey_id):
    """Add a response to a survey."""
    from .forms import SurveyResponseForm
    
    survey = get_object_or_404(Survey, id=survey_id)
    if request.method == 'POST':
        form = SurveyResponseForm(request.POST)
        if form.is_valid():
            response = form.save(commit=False)
            response.survey = survey
            response.save()
            return redirect('survey_detail', survey_id=survey_id)
    else:
        form = SurveyResponseForm()
    
    return render(request, 'shops/survey_response_form.html', {
        'form': form,
        'survey': survey,
        'action': 'Add'
    })


def edit_survey_response(request, response_id):
    """Edit a survey response."""
    from .forms import SurveyResponseForm
    
    response = get_object_or_404(SurveyResponse, id=response_id)
    survey = response.survey
    
    if request.method == 'POST':
        form = SurveyResponseForm(request.POST, instance=response)
        if form.is_valid():
            form.save()
            return redirect('survey_detail', survey_id=survey.id)
    else:
        form = SurveyResponseForm(instance=response)
    
    return render(request, 'shops/survey_response_form.html', {
        'form': form,
        'survey': survey,
        'response': response,
        'action': 'Edit'
    })


def delete_survey_response(request, response_id):
    """Delete a survey response."""
    response = get_object_or_404(SurveyResponse, id=response_id)
    survey_id = response.survey.id
    
    if request.method == 'POST':
        response.delete()
        return redirect('survey_detail', survey_id=survey_id)
    
    return render(request, 'shops/survey_response_confirm_delete.html', {'response': response})


def _period_key(row):
    """Sort survey periods like "May-26" or "2026-05" by date; anything unrecognised sorts after, by name."""
    from datetime import datetime
    for fmt in ('%b-%y', '%B-%y', '%b %y', '%b %Y', '%B %Y', '%Y-%m', '%m/%Y'):
        try:
            return (0, datetime.strptime(row['name'], fmt), '')
        except ValueError:
            pass
    return (1, datetime.min, row['name'])


def survey_analysis(request, survey_id):
    """Brand distribution and shelf-price charts for a survey, filterable by region, location and period."""
    survey = get_object_or_404(Survey, id=survey_id)
    all_responses = survey.responses.all()
    filters = {f: request.GET.get(f, '').strip() for f in ('region', 'location', 'period')}
    responses = all_responses.filter(**{f: v for f, v in filters.items() if v})

    has_store = ~Q(customer='')
    has_brand = ~Q(product='')
    store_total = responses.filter(has_store).values('customer').distinct().count()

    def num(v, places=2):
        return round(float(v), places) if v is not None else None

    brands = [{
        'name': r['product'], 'stores': r['stores'], 'responses': r['n'],
        'pct': round(100 * r['stores'] / store_total, 1) if store_total else 0,
        'max_price': num(r['max_price']), 'min_price': num(r['min_price']), 'avg_price': num(r['avg_price']),
        'qty': r['qty'] or 0,
    } for r in responses.filter(has_brand).values('product').annotate(
        stores=Count('customer', distinct=True, filter=has_store), n=Count('id'),
        max_price=Max('price'), min_price=Min('price'), avg_price=Avg('price'), qty=Sum('quantity'),
    ).order_by('-stores', 'product')]

    stores = [{'name': r['customer'], 'brands': r['brands'], 'qty': r['qty'] or 0}
              for r in responses.filter(has_store).values('customer').annotate(
                  brands=Count('product', distinct=True, filter=has_brand), qty=Sum('quantity'),
              ).order_by('-brands', 'customer')]

    def by(field):
        return [{'name': r[field], 'stores': r['stores'], 'brands': r['brands'], 'avg_price': num(r['avg_price']),
                 'qty': r['qty'] or 0}
                for r in responses.exclude(**{field: ''}).values(field).annotate(
                    stores=Count('customer', distinct=True, filter=has_store),
                    brands=Count('product', distinct=True, filter=has_brand),
                    avg_price=Avg('price'), qty=Sum('quantity'),
                ).order_by(field)]

    stats = {
        'responses': responses.count(),
        'stores': store_total,
        'brands': len(brands),
        'avg_price': responses.aggregate(v=Avg('price'))['v'],
        'total_qty': responses.aggregate(v=Sum('quantity'))['v'],
        'avg_brands_per_store': (sum(s['brands'] for s in stores) / len(stores)) if stores else None,
    }

    def options(field):
        return all_responses.exclude(**{field: ''}).values_list(field, flat=True).distinct().order_by(field)

    return render(request, 'shops/survey_analysis.html', {
        'survey': survey,
        'stats': stats,
        'filters': filters,
        'filter_options': {f: options(f) for f in filters},
        'chart_data': {'brands': brands, 'stores': stores, 'regions': by('region'),
                       'locations': by('location'), 'periods': sorted(by('period'), key=_period_key),
                       'store_total': store_total},
    })


def _import_survey_csv(request, survey, csv_file):
    """Add one SurveyResponse per CSV row to the survey and show the result page."""
    try:
        reader = csv.DictReader(StringIO(csv_file.read().decode('utf-8-sig')))
        imported = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            row = {(k or '').strip().lower(): (v or '').strip() for k, v in row.items()}
            try:
                values = {field: row.get(col, '') for col, field in SURVEY_CSV_FIELDS.items()}
                if not any(values.values()):
                    continue  # blank line
                values['price'] = float(values['price'].replace(',', '')) if values['price'] else None
                values['quantity'] = int(values['quantity'].replace(',', '')) if values['quantity'] else None
                SurveyResponse.objects.create(survey=survey, recorded_by=row.get('recorded_by') or 'Bulk Import', **values)
                imported += 1
            except Exception as e:
                errors.append(f'Row {row_num}: {str(e)}')

        return render(request, 'shops/survey_import_result.html', {
            'survey': survey,
            'imported': imported,
            'errors': errors,
        })
    except Exception as e:
        return render(request, 'shops/survey_import_result.html', {
            'survey': survey,
            'error': f'Error processing file: {str(e)}',
        })


def _survey_import_page(request, form, survey=None):
    return render(request, 'shops/survey_import.html', {
        'form': form,
        'survey': survey,
        'template_columns': SURVEY_CSV_COLUMNS,
        'template_examples': SURVEY_CSV_EXAMPLES,
    })


def import_survey_responses(request, survey_id):
    """Bulk import survey responses from CSV file."""
    survey = get_object_or_404(Survey, id=survey_id)

    if request.method == 'POST':
        form = BulkSurveyResponseForm(request.POST, request.FILES)
        if form.is_valid():
            return _import_survey_csv(request, survey, request.FILES['csv_file'])
    else:
        form = BulkSurveyResponseForm()

    return _survey_import_page(request, form, survey)


def import_surveys(request):
    """CSV import from the Surveys list: into an existing survey, or a new one created from the form."""
    from .forms import SurveyCSVImportForm

    if request.method == 'POST':
        form = SurveyCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            survey = form.cleaned_data['survey']
            if survey is None:
                survey = Survey.objects.create(
                    title=form.cleaned_data['new_title'].strip(),
                    category=form.cleaned_data['new_category'] or 'Product Performance',
                    created_by=request.user.username if request.user.is_authenticated else 'Anonymous',
                )
            return _import_survey_csv(request, survey, request.FILES['csv_file'])
    else:
        form = SurveyCSVImportForm(initial={'survey': request.GET.get('survey')})

    return _survey_import_page(request, form)
