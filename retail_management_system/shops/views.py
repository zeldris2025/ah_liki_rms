import csv
import json
import os
import zipfile
from datetime import date

from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Business, BusinessPhoto, Shop, ShopPhoto, Sponsorship, SponsorshipPhoto


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

    region_data = [
        {'label': r, 'value': shops.filter(region=r).count()}
        for r in ['Region 1', 'Region 2', 'Region 3', 'Region 4']
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
        'region_data': json.dumps(region_data),
        'biz_data': json.dumps(biz_data),
        'recent_shops': recent_shops,
    }
    return render(request, 'shops/dashboard.html', ctx)


# ══════════════════════════════════════════════════════════════════════════════
# SHOPS
# ══════════════════════════════════════════════════════════════════════════════

def shop_list(request):
    qs = Shop.objects.prefetch_related('photos').all()

    q       = request.GET.get('q', '').strip()
    island  = request.GET.get('island', '')
    region  = request.GET.get('region', '')
    tip_top = request.GET.get('tip_top', '')
    photos  = request.GET.get('photos', '')

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(owner__icontains=q))
    if island:
        qs = qs.filter(island=island)
    if region:
        qs = qs.filter(region=region)
    if tip_top == 'yes':
        qs = qs.filter(tip_top=True)
    elif tip_top == 'no':
        qs = qs.filter(tip_top=False)
    if photos == 'yes':
        qs = qs.filter(photos__isnull=False).distinct()
    elif photos == 'no':
        qs = qs.filter(photos__isnull=True)

    paginator = Paginator(qs, 12)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'shops/shop_list.html', {
        'page_obj': page_obj,
        'total': qs.count(),
        'q': q, 'island': island, 'region': region,
        'tip_top': tip_top, 'photos': photos,
    })


def shop_detail(request, shop_id):
    shop = get_object_or_404(Shop.objects.prefetch_related('photos'), id=shop_id)
    # Group photos by note for the detail view
    groups = {}
    for p in shop.photos.all():
        key = p.note.strip() if p.note.strip() else 'Unlabelled'
        groups.setdefault(key, []).append(p)
    return render(request, 'shops/shop_detail.html', {'shop': shop, 'photo_groups': groups})


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
            region  = request.POST.get('region', 'Region 1'),
            tip_top = 'tip_top' in request.POST,
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
        shop.region  = request.POST.get('region', shop.region)
        shop.tip_top = 'tip_top' in request.POST
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


def upolu_shops(request, region):
    qs = Shop.objects.prefetch_related('photos').filter(island='Upolu', region=region)
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
        'page_obj': page_obj, 'region': region, 'island': 'Upolu'
    })


def savaii_shops(request, region):
    qs = Shop.objects.prefetch_related('photos').filter(island='Savaii', region=region)
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
        'page_obj': page_obj, 'region': region, 'island': 'Savaii'
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
    region      = request.GET.get('region', '')
    status      = request.GET.get('status', '')

    response = HttpResponse(content_type='text/csv')

    if report_type == 'shops':
        qs = Shop.objects.prefetch_related('photos').all()
        if island: qs = qs.filter(island=island)
        if region: qs = qs.filter(region=region)
        response['Content-Disposition'] = f'attachment; filename="shops_report_{date.today()}.csv"'
        w = csv.writer(response)
        w.writerow(['ID', 'Name', 'Owner', 'Phone', 'Address', 'Island', 'Region', 'Tip Top', 'Photo Count', 'Created'])
        for s in qs:
            w.writerow([s.pk, s.name, s.owner, s.phone, s.address, s.island, s.region,
                        'Yes' if s.tip_top else 'No', s.photos.count(), s.created])

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
