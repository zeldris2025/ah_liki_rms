import csv
import json
import os
import zipfile
from datetime import date
from io import StringIO, BytesIO

from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q, Sum, Count, Avg, F
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from tablib import Dataset

from .models import Business, BusinessPhoto, Shop, ShopPhoto, Sponsorship, SponsorshipPhoto, Survey, SurveyResponse, ShopSales
from .forms import ShopCSVImportForm, BusinessCSVImportForm, SponsorshipCSVImportForm, SurveyForm, SurveyResponseForm, BulkSurveyResponseForm, SalesCSVImportForm
from .admin import ShopResource, BusinessResource, SponsorshipResource


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
    biz_data = [
        {'label': t, 'value': businesses.filter(business_type=t).count()}
        for t in ['HOTEL', 'CAFE', 'RESTAURANT', 'OTHER']
    ]
    recent_shops = list(shops.order_by('-id')[:6])

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
        'recent_shops': recent_shops,
    }
    return render(request, 'shops/dashboard.html', ctx)


# ══════════════════════════════════════════════════════════════════════════════
# SHOPS
# ══════════════════════════════════════════════════════════════════════════════

def shop_list(request):
    qs = Shop.objects.prefetch_related('photos').all()

    q           = request.GET.get('q', '').strip()
    territories = request.GET.getlist('territory')
    tip_top     = request.GET.get('tip_top', '')
    taula       = request.GET.get('taula_fridge', '')
    talofa      = request.GET.get('talofa_voucher', '')
    faakau      = request.GET.get('faakau_com', '')
    photos      = request.GET.get('photos', '')

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(owner__icontains=q))
    if territories:
        qs = qs.filter(territory__in=territories)
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

    paginator = Paginator(qs, 12)
    page_obj  = paginator.get_page(request.GET.get('page'))

    all_territories = ['EC1', 'EC2', 'EC3', 'LFG', 'VT1', 'VT2', 'VT3', 'WC1', 'WC2', 'WC4']

    return render(request, 'shops/shop_list.html', {
        'page_obj': page_obj,
        'total': qs.count(),
        'q': q, 'territories': territories,
        'all_territories': all_territories,
        'tip_top': tip_top, 'photos': photos,
        'taula_fridge': taula, 'talofa_voucher': talofa, 'faakau_com': faakau,
    })


def shop_detail(request, shop_id):
    shop = get_object_or_404(Shop.objects.prefetch_related('photos', 'sales'), id=shop_id)
    # Group photos by note for the detail view
    groups = {}
    for p in shop.photos.all():
        key = p.note.strip() if p.note.strip() else 'Unlabelled'
        groups.setdefault(key, []).append(p)

    sales_qs = shop.sales.all()
    filter_month = request.GET.get('month', '')
    filter_year = request.GET.get('year', '')

    if filter_year:
        sales_qs = sales_qs.filter(date__year=filter_year)
    if filter_month:
        sales_qs = sales_qs.filter(date__month=filter_month)

    total_sales = sales_qs.aggregate(total=Sum('total_sales'))['total'] or 0
    total_quantity = sales_qs.aggregate(total=Sum('quantity'))['total'] or 0

    available_years = sorted(set(
        s.date.year for s in shop.sales.all() if s.date
    ), reverse=True)

    return render(request, 'shops/shop_detail.html', {
        'shop': shop,
        'photo_groups': groups,
        'sales': sales_qs,
        'total_sales': total_sales,
        'total_quantity': total_quantity,
        'sales_count': sales_qs.count(),
        'filter_month': filter_month,
        'filter_year': filter_year,
        'available_years': available_years,
        'months': [(1,'Jan'),(2,'Feb'),(3,'Mar'),(4,'Apr'),(5,'May'),(6,'Jun'),
                   (7,'Jul'),(8,'Aug'),(9,'Sep'),(10,'Oct'),(11,'Nov'),(12,'Dec')],
    })


def add_shop(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            return render(request, 'shops/shop_form.html', {
                'error': 'Shop name is required', 'action': 'Add', 'form_data': request.POST
            })
        shop = Shop.objects.create(
            name    = name,
            owner   = request.POST.get('owner', ''),
            phone   = request.POST.get('phone', ''),
            address = request.POST.get('address', ''),
            island  = request.POST.get('island', 'Upolu'),
            territory = request.POST.get('territory', '') or None,
            tip_top = 'tip_top' in request.POST,
            taula_fridge = 'taula_fridge' in request.POST,
            talofa_voucher = 'talofa_voucher' in request.POST,
            faakau_com = 'faakau_com' in request.POST,
        )
        # Handle photos with individual labels
        images = request.FILES.getlist('images')
        labels = request.POST.getlist('image_labels')
        for idx, img in enumerate(images):
            label = labels[idx] if idx < len(labels) else ''
            ShopPhoto.objects.create(shop=shop, image=img, note=label.strip())
        return redirect('shop_list')
    return render(request, 'shops/shop_form.html', {'action': 'Add'})


def edit_shop(request, shop_id):
    shop = get_object_or_404(Shop.objects.prefetch_related('photos'), id=shop_id)
    if request.method == 'POST':
        if 'delete_shop' in request.POST:
            shop.delete()
            return redirect('shop_list')
        # Update fields
        shop.name    = request.POST.get('name', shop.name).strip() or shop.name
        shop.owner   = request.POST.get('owner', shop.owner)
        shop.phone   = request.POST.get('phone', shop.phone)
        shop.address = request.POST.get('address', shop.address)
        shop.island  = request.POST.get('island', shop.island)
        shop.territory = request.POST.get('territory', '') or None
        shop.tip_top = 'tip_top' in request.POST
        shop.taula_fridge = 'taula_fridge' in request.POST
        shop.talofa_voucher = 'talofa_voucher' in request.POST
        shop.faakau_com = 'faakau_com' in request.POST
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
    return render(request, 'shops/shop_form.html', {'action': 'Edit', 'shop': shop})


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
# HORECCA
# ══════════════════════════════════════════════════════════════════════════════

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
    })


def delete_sponsorship(request, sp_id):
    sp = get_object_or_404(Sponsorship, id=sp_id)
    sp.delete()
    return redirect('sponsorship_list')


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS / CSV DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

def reports(request):
    shops        = Shop.objects.prefetch_related('photos').all()
    businesses   = Business.objects.all()
    sponsorships = Sponsorship.objects.all()
    return render(request, 'shops/reports.html', {
        'shops': shops,
        'businesses': businesses,
        'sponsorships': sponsorships,
    })


def download_report(request):
    report_type = request.GET.get('type', 'shops')
    island      = request.GET.get('island', '')
    status      = request.GET.get('status', '')

    response = HttpResponse(content_type='text/csv')

    if report_type == 'shops':
        qs = Shop.objects.prefetch_related('photos').all()
        if island: qs = qs.filter(island=island)
        response['Content-Disposition'] = f'attachment; filename="shops_report_{date.today()}.csv"'
        w = csv.writer(response)
        w.writerow(['ID', 'Name', 'Owner', 'Phone', 'Address', 'Island', 'Territory', 'Tip Top', 'Taula Fridge', 'Talofa Voucher', 'Faakau.com', 'Photo Count', 'Created'])
        for s in qs:
            w.writerow([s.pk, s.name, s.owner, s.phone, s.address, s.island, s.territory or '',
                        'Yes' if s.tip_top else 'No', 'Yes' if s.taula_fridge else 'No', 'Yes' if s.talofa_voucher else 'No', 'Yes' if s.faakau_com else 'No',
                        s.photos.count(), s.created])

    elif report_type == 'horecca':
        qs = Business.objects.prefetch_related('photos').all()
        if island: qs = qs.filter(island=island)
        response['Content-Disposition'] = f'attachment; filename="horecca_report_{date.today()}.csv"'
        w = csv.writer(response)
        w.writerow(['ID', 'Name', 'Type', 'Island', 'Location', 'Photo Count', 'Created'])
        for b in qs:
            w.writerow([b.pk, b.name, b.business_type, b.island, b.location,
                        b.photos.count(), b.created_at.date()])

    else:  # sponsorships
        qs = Sponsorship.objects.prefetch_related('photos').all()
        if status: qs = qs.filter(status=status)
        response['Content-Disposition'] = f'attachment; filename="sponsorships_report_{date.today()}.csv"'
        w = csv.writer(response)
        w.writerow(['ID', 'Customer', 'Type', 'Value (WST)', 'Status', 'Start', 'End', 'Notes', 'Photo Count', 'Created'])
        for s in qs:
            w.writerow([s.pk, s.customer, s.type, s.value, s.status,
                        s.start or '', s.end or '', s.notes, s.photos.count(), s.created])

    return response


# ══════════════════════════════════════════════════════════════════════════════
# CSV IMPORT
# ══════════════════════════════════════════════════════════════════════════════

@login_required(login_url='login')
def import_shops(request):
    """Import shops from CSV file, with optional sales columns."""
    from datetime import datetime

    if request.method == 'POST':
        form = ShopCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                decoded = csv_file.read().decode('utf-8')
                reader = csv.DictReader(StringIO(decoded))
                imported = 0
                updated = 0
                skipped = 0
                sales_added = 0
                errors = []

                def truthy(v):
                    return str(v).strip().upper() in ('TRUE', 'YES', '1', 'Y')

                TEXT_FIELDS = ('owner', 'phone', 'address', 'island', 'territory')
                BOOL_FIELDS = ('tip_top', 'taula_fridge', 'talofa_voucher', 'faakau_com')

                # Only columns actually present in the file are considered, so a
                # missing column never wipes a value on an existing shop.
                present = {(h or '').strip().lower() for h in (reader.fieldnames or [])}

                for row_num, row in enumerate(reader, start=2):
                    try:
                        name = (row.get('name') or '').strip()
                        if not name:
                            errors.append(f'Row {row_num}: missing shop name')
                            continue

                        shop = Shop.objects.filter(name__iexact=name).first()

                        if shop:
                            # Same name — compare each field and update only the
                            # ones that actually differ. Identical rows are skipped.
                            changes = {}
                            for field in TEXT_FIELDS:
                                if field not in present:
                                    continue
                                value = (row.get(field) or '').strip()
                                if not value:          # blank cell = leave as-is
                                    continue
                                if (getattr(shop, field) or '') != value:
                                    changes[field] = value
                            for field in BOOL_FIELDS:
                                if field not in present:
                                    continue
                                value = truthy(row.get(field, ''))
                                if getattr(shop, field) != value:
                                    changes[field] = value

                            if changes:
                                for field, value in changes.items():
                                    setattr(shop, field, value)
                                shop.save(update_fields=list(changes))
                                updated += 1
                            else:
                                skipped += 1
                        else:
                            shop = Shop.objects.create(
                                name=name,
                                owner=(row.get('owner') or '').strip() or None,
                                phone=(row.get('phone') or '').strip() or None,
                                address=(row.get('address') or '').strip() or None,
                                island=(row.get('island') or 'Upolu').strip() or 'Upolu',
                                territory=(row.get('territory') or '').strip() or None,
                                tip_top=truthy(row.get('tip_top', '')),
                                taula_fridge=truthy(row.get('taula_fridge', '')),
                                talofa_voucher=truthy(row.get('talofa_voucher', '')),
                                faakau_com=truthy(row.get('faakau_com', '')),
                            )
                            imported += 1

                        # Optional sales columns
                        products = (row.get('products') or '').strip() or None
                        qty_str = (row.get('quantity') or '').strip()
                        total_str = (row.get('total_sales') or '').strip()
                        date_str = (row.get('date') or '').strip()

                        if products or qty_str or total_str or date_str:
                            sale_date = None
                            if date_str:
                                for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                                    try:
                                        sale_date = datetime.strptime(date_str, fmt).date()
                                        break
                                    except ValueError:
                                        continue
                            exists = sale_date and products and ShopSales.objects.filter(
                                shop=shop, date=sale_date, products=products
                            ).exists()
                            if not exists:
                                ShopSales.objects.create(
                                    shop=shop,
                                    products=products,
                                    quantity=int(qty_str) if qty_str else None,
                                    total_sales=float(total_str) if total_str else None,
                                    date=sale_date,
                                )
                                sales_added += 1
                    except Exception as e:
                        errors.append(f'Row {row_num}: {str(e)}')

                return render(request, 'shops/import_result.html', {
                    'model_type': 'Shops',
                    'messages': {
                        'success': f'Imported {imported} new shops, updated {updated} existing, '
                                   f'skipped {skipped} unchanged, added {sales_added} sales records.',
                        'errors': errors,
                        'import_count': imported,
                        'update_count': updated,
                    },
                    'success': not errors,
                })
            except Exception as e:
                return render(request, 'shops/import_shops.html', {
                    'form': form,
                    'error': f'Error processing file: {str(e)}'
                })
    else:
        form = ShopCSVImportForm()

    return render(request, 'shops/import_shops.html', {'form': form})


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
    """Import sponsorships from CSV file."""
    if request.method == 'POST':
        form = SponsorshipCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                # Read and parse CSV
                dataset = Dataset().load(csv_file.read().decode('utf-8'), 'csv')
                resource = SponsorshipResource()
                result = resource.import_data(dataset, dry_run=False)

                error_list = []
                if result.has_errors():
                    for error in result.errors:
                        error_list.append(str(error))

                messages = {
                    'success': f'Successfully imported {result.total_rows} sponsorships.',
                    'errors': error_list,
                    'import_count': result.total_rows,
                }
                return render(request, 'shops/import_result.html', {
                    'model_type': 'Sponsorships',
                    'messages': messages,
                    'success': not result.has_errors(),
                })
            except Exception as e:
                return render(request, 'shops/import_sponsorships.html', {
                    'form': form,
                    'error': f'Error processing file: {str(e)}'
                })
    else:
        form = SponsorshipCSVImportForm()

    return render(request, 'shops/import_sponsorships.html', {'form': form})


@login_required(login_url='login')
def import_shop_sales(request, shop_id):
    """Import sales data for a specific shop from CSV."""
    from datetime import datetime

    shop = get_object_or_404(Shop, id=shop_id)

    if request.method == 'POST':
        form = SalesCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                decoded = csv_file.read().decode('utf-8')
                reader = csv.DictReader(StringIO(decoded))
                imported = 0
                skipped = 0
                errors = []

                for row_num, row in enumerate(reader, start=2):
                    try:
                        date_str = (row.get('date') or '').strip()
                        sale_date = None
                        if date_str:
                            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                                try:
                                    sale_date = datetime.strptime(date_str, fmt).date()
                                    break
                                except ValueError:
                                    continue

                        products = (row.get('products') or '').strip() or None
                        qty_str = (row.get('quantity') or '').strip()
                        total_str = (row.get('total_sales') or '').strip()

                        if sale_date and products and ShopSales.objects.filter(
                            shop=shop, date=sale_date, products=products
                        ).exists():
                            skipped += 1
                            continue

                        ShopSales.objects.create(
                            shop=shop,
                            products=products,
                            quantity=int(qty_str) if qty_str else None,
                            total_sales=float(total_str) if total_str else None,
                            date=sale_date,
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f'Row {row_num}: {str(e)}')

                return render(request, 'shops/sales_import_result.html', {
                    'shop': shop,
                    'imported': imported,
                    'skipped': skipped,
                    'errors': errors,
                })
            except Exception as e:
                return render(request, 'shops/import_sales.html', {
                    'form': form, 'shop': shop,
                    'error': f'Error processing file: {str(e)}'
                })
    else:
        form = SalesCSVImportForm()

    return render(request, 'shops/import_sales.html', {'form': form, 'shop': shop})


def download_sales_template(request):
    """Download CSV template for shop sales."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_template.csv"'
    w = csv.writer(response)
    w.writerow(['products', 'quantity', 'total_sales', 'date'])
    w.writerow(['Coca Cola 1.5L', '24', '120.00', '2026-01-15'])
    return response


def download_shop_template(request):
    """Download CSV template for shops."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shops_template.csv"'
    w = csv.writer(response)
    w.writerow(['name', 'owner', 'phone', 'address', 'island', 'territory', 'tip_top', 'taula_fridge', 'talofa_voucher',
                'faakau_com', 'products', 'quantity', 'total_sales', 'date'])
    w.writerow(['Example Shop', 'Shop Owner', '+685-1234567', '123 Main Street', 'Upolu', 'EC1', 'FALSE', 'FALSE', 'FALSE',
                'FALSE', 'Coca Cola 1.5L', '24', '120.00', '2026-01-15'])
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
    w.writerow(['customer', 'type', 'value', 'status', 'start', 'end', 'notes'])
    w.writerow(['Company Name', 'Signage', '5000', 'Active', '2026-01-01', '2026-12-31', 'Annual sponsorship'])
    return response


def download_survey_template(request):
    """Download CSV template for survey responses."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="survey_responses_template.csv"'
    w = csv.writer(response)
    # Header row with column names
    w.writerow(['product', 'category', 'customer', 'location', 'region', 'week', 'price', 'quantity', 'rating', 'notes'])
    # Example row - category here is PRODUCT category (SODA, SNACK, etc), not survey category
    w.writerow(['Coca Cola', 'SODA', 'Samoa Store', 'UPOLU', '2', '21', '2.50', '12', '4', 'Best seller in stock'])
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
        'avg_rating': survey.responses.filter(rating__isnull=False).aggregate(Avg('rating'))['rating__avg'],
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


def survey_analysis(request, survey_id):
    """Display comprehensive analysis and charts for a survey."""
    survey = get_object_or_404(Survey.objects.prefetch_related('responses'), id=survey_id)
    responses = survey.responses.all()
    
    # Aggregated data for charts
    from django.db.models import Count, Sum, Avg
    
    # Chart 1: Responses by Location
    location_data = responses.values('location').filter(location__isnull=False).annotate(
        count=Count('id'),
        total_revenue=Sum('price')
    ).order_by('-count')[:10]
    
    # Chart 2: Responses by Region
    region_data = responses.values('region').filter(region__isnull=False).annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Chart 3: Price distribution
    price_data = responses.values('product').filter(price__isnull=False).annotate(
        avg_price=Avg('price'),
        count=Count('id')
    ).order_by('-avg_price')[:10]
    
    # Chart 4: Top products
    product_data = responses.values('product').filter(product__isnull=False).annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Chart 5: Ratings distribution
    rating_data = responses.values('rating').filter(rating__isnull=False).annotate(
        count=Count('id')
    ).order_by('rating')
    
    # Chart 6: Top categories
    category_data = responses.values('category').filter(category__isnull=False).annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Chart 7: Top customers (NEW)
    customer_data = responses.values('customer').filter(customer__isnull=False).annotate(
        count=Count('id'),
        total_qty=Sum('quantity')
    ).order_by('-count')[:10]
    
    # Chart 8: Weekly trends (NEW)
    weekly_data = responses.values('week').filter(week__isnull=False).annotate(
        count=Count('id'),
        total_qty=Sum('quantity'),
        avg_price=Avg('price')
    ).order_by('week')
    
    # Chart 9: Quantity by product (NEW)
    quantity_data = responses.values('product').filter(quantity__isnull=False).annotate(
        total_qty=Sum('quantity'),
        count=Count('id'),
        avg_qty=Avg('quantity')
    ).order_by('-total_qty')[:10]
    
    # Chart 10: Revenue by location (NEW)
    revenue_data = responses.values('location').filter(price__isnull=False, quantity__isnull=False).annotate(
        total_revenue=Sum(F('price') * F('quantity'), output_field=models.FloatField()),
        count=Count('id')
    ).order_by('-total_revenue')[:10]
    
    # Chart 11: Rating by category (NEW)
    category_rating_data = responses.values('category').filter(rating__isnull=False).annotate(
        avg_rating=Avg('rating'),
        count=Count('id')
    ).order_by('-avg_rating')[:10]
    
    # Summary stats
    stats = {
        'total_responses': responses.count(),
        'avg_price': responses.filter(price__isnull=False).aggregate(Avg('price'))['price__avg'],
        'avg_rating': responses.filter(rating__isnull=False).aggregate(Avg('rating'))['rating__avg'],
        'total_quantity': responses.filter(quantity__isnull=False).aggregate(Sum('quantity'))['quantity__sum'],
        'unique_locations': responses.filter(location__isnull=False).values('location').distinct().count(),
        'unique_regions': responses.filter(region__isnull=False).values('region').distinct().count(),
        'total_revenue': responses.filter(price__isnull=False, quantity__isnull=False).aggregate(
            total=Sum(F('price') * F('quantity'), output_field=models.FloatField())
        )['total'],
        'unique_customers': responses.filter(customer__isnull=False).values('customer').distinct().count(),
    }
    
    return render(request, 'shops/survey_analysis.html', {
        'survey': survey,
        'stats': stats,
        'location_data': list(location_data),
        'region_data': list(region_data),
        'price_data': list(price_data),
        'product_data': list(product_data),
        'rating_data': list(rating_data),
        'category_data': list(category_data),
        'customer_data': list(customer_data),
        'weekly_data': list(weekly_data),
        'quantity_data': list(quantity_data),
        'revenue_data': list(revenue_data),
        'category_rating_data': list(category_rating_data),
    })


def import_survey_responses(request, survey_id):
    """Bulk import survey responses from CSV file."""
    from .forms import BulkSurveyResponseForm
    import csv as csvmodule
    
    survey = get_object_or_404(Survey, id=survey_id)
    
    if request.method == 'POST':
        form = BulkSurveyResponseForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                decoded_file = csv_file.read().decode('utf-8')
                reader = csvmodule.DictReader(StringIO(decoded_file))
                imported = 0
                errors = []
                
                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Map CSV columns to model fields
                        SurveyResponse.objects.create(
                            survey=survey,
                            product=row.get('product', '').strip() or None,
                            category=row.get('category', '').strip() or None,
                            customer=row.get('customer', '').strip() or None,
                            location=row.get('location', '').strip() or None,
                            region=row.get('region', '').strip() or None,
                            week=int(row.get('week', 0)) if row.get('week') else None,
                            price=float(row.get('price', 0)) if row.get('price') else None,
                            quantity=int(row.get('quantity', 0)) if row.get('quantity') else None,
                            rating=int(row.get('rating', 0)) if row.get('rating') else None,
                            notes=row.get('notes', '').strip() or '',
                            recorded_by=row.get('recorded_by', 'Bulk Import').strip(),
                        )
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
    else:
        form = BulkSurveyResponseForm()
    
    return render(request, 'shops/survey_import.html', {
        'form': form,
        'survey': survey,
    })
