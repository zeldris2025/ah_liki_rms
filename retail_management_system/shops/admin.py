from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import Shop, ShopPhoto, Business, BusinessPhoto, Sponsorship, SponsorshipPhoto, ShopSales


# ── Import/Export Resources ───────────────────────────────────────────────────

class ShopResource(resources.ModelResource):
    class Meta:
        model = Shop
        fields = ('id', 'name', 'owner', 'phone', 'address', 'island', 'territory', 'tip_top', 'taula_fridge', 'talofa_voucher', 'faakau_com', 'created')
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        # Check if shop with this name already exists
        name = row.get('name', '').strip()
        if name and Shop.objects.filter(name__iexact=name).exists():
            # Skip this row if shop already exists
            return True
        return False


class BusinessResource(resources.ModelResource):
    class Meta:
        model = Business
        fields = ('id', 'name', 'business_type', 'island', 'location', 'created_at', 'updated_at')
        export_order = fields


class SponsorshipResource(resources.ModelResource):
    class Meta:
        model = Sponsorship
        fields = ('id', 'customer', 'type', 'value', 'status', 'start', 'end', 'notes', 'created')
        export_order = fields


class SalesResource(resources.ModelResource):
    class Meta:
        model = ShopSales
        fields = ('id', 'shop', 'products', 'quantity', 'total_sales', 'date', 'created_at')
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        shop_name = row.get('shop', '').strip()
        date = row.get('date', '').strip()
        if shop_name and date:
            try:
                shop = Shop.objects.get(name__iexact=shop_name)
                from datetime import datetime
                sale_date = datetime.strptime(date, '%Y-%m-%d').date()
                if ShopSales.objects.filter(shop=shop, date=sale_date).exists():
                    return True
            except:
                pass
        return False


class ShopPhotoInline(admin.TabularInline):
    model = ShopPhoto
    extra = 1
    fields = ('image', 'note', 'preview')
    readonly_fields = ('preview',)

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" height="60" style="object-fit:cover;border-radius:4px">', obj.image.url)
        return "—"
    preview.short_description = "Preview"


@admin.register(Shop)
class ShopAdmin(ImportExportModelAdmin):
    resource_class = ShopResource
    inlines = [ShopPhotoInline]
    list_display  = ('name', 'owner', 'phone', 'island', 'territory', 'tip_top', 'taula_fridge', 'talofa_voucher', 'faakau_com', 'photo_count')
    list_filter   = ('island', 'territory', 'tip_top', 'taula_fridge', 'talofa_voucher', 'faakau_com')
    search_fields = ('name', 'owner')

    def photo_count(self, obj):
        return obj.photos.count()
    photo_count.short_description = "Photos"


class BusinessPhotoInline(admin.TabularInline):
    model = BusinessPhoto
    extra = 1
    fields = ('image', 'note', 'preview')
    readonly_fields = ('preview',)

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" height="60" style="object-fit:cover;border-radius:4px">', obj.image.url)
        return "—"
    preview.short_description = "Preview"


@admin.register(Business)
class BusinessAdmin(ImportExportModelAdmin):
    resource_class = BusinessResource
    inlines = [BusinessPhotoInline]
    list_display  = ('name', 'business_type', 'island', 'location', 'photo_count', 'created_at')
    list_filter   = ('business_type', 'island')
    search_fields = ('name', 'location')

    def photo_count(self, obj):
        return obj.photos.count()
    photo_count.short_description = "Photos"


class SponsorshipPhotoInline(admin.TabularInline):
    model = SponsorshipPhoto
    extra = 1
    fields = ('image', 'note', 'preview')
    readonly_fields = ('preview',)

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" height="60" style="object-fit:cover;border-radius:4px">', obj.image.url)
        return "—"
    preview.short_description = "Preview"


@admin.register(Sponsorship)
class SponsorshipAdmin(ImportExportModelAdmin):
    resource_class = SponsorshipResource
    inlines = [SponsorshipPhotoInline]
    list_display  = ('customer', 'type', 'value', 'status', 'start', 'end', 'photo_count')
    list_filter   = ('status', 'type')
    search_fields = ('customer', 'notes')

    def photo_count(self, obj):
        return obj.photos.count()
    photo_count.short_description = "Photos"


@admin.register(ShopSales)
class ShopSalesAdmin(ImportExportModelAdmin):
    resource_class = SalesResource
    list_display  = ('shop', 'products', 'quantity', 'total_sales', 'date')
    list_filter   = ('date', 'shop__territory')
    search_fields = ('shop__name', 'products')
    date_hierarchy = 'date'
    
    
admin.site.site_header = "Retail Management System"
admin.site.site_title = "Retail Management Admin"
admin.site.index_title = "Retail Management Admin"