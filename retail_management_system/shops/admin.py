from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from import_export.fields import Field
from import_export.widgets import DateWidget
from django import forms

from .models import (Shop, ShopPhoto, Business, BusinessPhoto, Sponsorship, SponsorshipPhoto, MonthlySales, Promotion,
                     SalesTarget, SalesRep, CustomerProductSales)


# ── Import/Export Resources ───────────────────────────────────────────────────

class ShopResource(resources.ModelResource):
    """Admin export of clients. For uploads use Bulk Import → Import Clients, which matches by Customer Code."""
    class Meta:
        model = Shop
        fields = ('customer_code', 'name', 'customer_type', 'contact_person', 'address', 'island', 'phone',
                  'territory', 'email', 'tip_top', 'taula_fridge', 'talofa_voucher', 'faakau_com', 'created')
        export_order = fields
        import_id_fields = ('customer_code',)
        skip_unchanged = True
        report_skipped = True


class BusinessResource(resources.ModelResource):
    class Meta:
        model = Business
        fields = ('id', 'name', 'business_type', 'island', 'location', 'created_at', 'updated_at')
        export_order = fields


class SponsorshipResource(resources.ModelResource):
    class Meta:
        model = Sponsorship
        fields = ('id', 'customer', 'type', 'sponsorship_type', 'value', 'status', 'start', 'end', 'notes', 'created')
        export_order = fields


class FlexibleDateWidget(DateWidget):
    """Accepts 2026-10-01, 01/10/2026 or 01-10-2026 (day first), plus real dates from Excel files."""
    FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y')

    def __init__(self):
        super().__init__(format='%Y-%m-%d')

    def clean(self, value, row=None, **kwargs):
        from datetime import date, datetime
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        value = str(value or '').strip()
        if not value:
            return None
        for fmt in self.FORMATS:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        raise ValueError(f'"{value}" is not a date. Use YYYY-MM-DD, e.g. 2026-10-01')


class PromotionResource(resources.ModelResource):
    """Promotions import/export in the admin. Rows match an existing promotion by company + name."""
    name       = Field(attribute='name',       column_name='Promotion Name')
    company    = Field(attribute='company',    column_name='Company')
    details    = Field(attribute='details',    column_name='Details')
    prizes     = Field(attribute='prizes',     column_name='Prizes')
    start_date = Field(attribute='start_date', column_name='Start Date', widget=FlexibleDateWidget())
    end_date   = Field(attribute='end_date',   column_name='End Date',   widget=FlexibleDateWidget())
    status     = Field(attribute='status',     column_name='Status', readonly=True)   # export only; set by the dates

    class Meta:
        model = Promotion
        fields = ('name', 'company', 'details', 'prizes', 'start_date', 'end_date', 'status')
        export_order = fields
        import_id_fields = ('company', 'name')
        clean_model_instances = True   # rejects unknown companies with a clear row error
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        # Tidy spacing and match company names regardless of capitals ("taula" -> "Taula")
        for key in ('Promotion Name', 'Company'):
            if row.get(key) is not None:
                row[key] = str(row[key]).strip()
        companies = {c.lower(): c for c, _ in Promotion.COMPANY_CHOICES}
        if row.get('Company'):
            row['Company'] = companies.get(row['Company'].lower(), row['Company'])
        # Excel exports blank cells as None; store them as empty text
        for key in ('Details', 'Prizes'):
            if row.get(key) is None:
                row[key] = ''


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
    list_display  = ('customer_code', 'name', 'customer_type', 'contact_person', 'phone', 'island', 'territory', 'photo_count')
    list_filter   = ('island', 'territory', 'customer_type', 'tip_top', 'taula_fridge', 'talofa_voucher', 'faakau_com')
    search_fields = ('customer_code', 'name', 'contact_person', 'email')

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
    list_display  = ('customer', 'type', 'sponsorship_type', 'value', 'status', 'start', 'end', 'photo_count')
    list_filter   = ('status', 'type', 'sponsorship_type')
    search_fields = ('customer', 'notes')

    def photo_count(self, obj):
        return obj.photos.count()
    photo_count.short_description = "Photos"


@admin.register(CustomerProductSales)
class CustomerProductSalesAdmin(admin.ModelAdmin):
    list_display  = ('shop', 'product_code', 'product_name', 'month', 'sales', 'updated_at')
    list_filter   = ('month',)
    search_fields = ('shop__customer_code', 'shop__name', 'product_code', 'product_name')
    raw_id_fields = ('shop',)
    date_hierarchy = 'month'


@admin.register(MonthlySales)
class MonthlySalesAdmin(admin.ModelAdmin):
    list_display  = ('customer_code', 'customer_name', 'month', 'sales', 'updated_at')
    list_filter   = ('month',)
    search_fields = ('shop__customer_code', 'shop__name')
    raw_id_fields = ('shop',)
    date_hierarchy = 'month'

    @admin.display(ordering='shop__customer_code')
    def customer_code(self, obj):
        return obj.shop.customer_code

    @admin.display(ordering='shop__name')
    def customer_name(self, obj):
        return obj.shop.name


class SalesRepForm(forms.ModelForm):
    class Meta:
        model = SalesRep
        fields = '__all__'
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color', 'style': 'width:70px;height:34px;padding:2px'}),
            'customer_types': forms.Textarea(attrs={'rows': 3, 'cols': 70}),
            'streams': forms.TextInput(attrs={'size': 70}),
        }


@admin.register(SalesRep)
class SalesRepAdmin(admin.ModelAdmin):
    """Corporate account managers shown on the Corporate Sales page."""
    form = SalesRepForm
    list_display  = ('name', 'user', 'colour', 'streams', 'customer_types', 'client_count', 'order', 'active')
    list_editable = ('order', 'active')
    list_display_links = ('name',)
    search_fields = ('name', 'streams', 'customer_types')
    fieldsets = (
        (None, {'fields': ('name', 'key', 'user', 'color', 'order', 'active')}),
        ('Clients', {'fields': ('streams', 'customer_types', 'matched_types'),
                     'description': 'A client is this rep’s when its Customer Type contains one of the keywords. '
                                    'If two reps match the same type, the one higher in the order gets it.'}),
    )
    readonly_fields = ('matched_types',)

    def get_readonly_fields(self, request, obj=None):
        # the key is used in page links and saved targets, so it's fixed once created
        return self.readonly_fields + (('key',) if obj else ())

    def _ownership(self):
        if not hasattr(self, '_owned'):
            from . import corporate
            ids, types, _ = corporate.client_ids_by_manager()
            self._owned = (ids, types)
        return self._owned

    def changelist_view(self, request, extra_context=None):
        self.__dict__.pop('_owned', None)   # recount on each visit
        return super().changelist_view(request, extra_context)

    @admin.display(description='Colour')
    def colour(self, obj):
        return format_html('<span style="display:inline-block;width:22px;height:22px;border-radius:50%;background:{}"></span>', obj.color)

    @admin.display(description='Clients')
    def client_count(self, obj):
        if not obj.active:
            return '—'
        return len(self._ownership()[0].get(obj.key, []))

    @admin.display(description='Customer types matched now')
    def matched_types(self, obj):
        self.__dict__.pop('_owned', None)
        if not obj or not obj.pk:
            return 'Save first to see which customer types this rep picks up.'
        if not obj.active:
            return 'Inactive, so no clients are counted.'
        ids, types = self._ownership()
        found = sorted(types.get(obj.key, []))
        if not found:
            return 'No customer types match yet.'
        return format_html('{} client(s): {}', len(ids.get(obj.key, [])), ', '.join(found))


class SalesTargetForm(forms.ModelForm):
    manager = forms.ChoiceField(label='Sales rep')

    class Meta:
        model = SalesTarget
        fields = ('manager', 'month', 'amount')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['manager'].choices = [(r.key, r.name) for r in SalesRep.objects.all()]
        self.fields['month'].help_text = 'Any day in the month; it’s saved as the 1st.'

    def clean_month(self):
        return self.cleaned_data['month'].replace(day=1)


@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    form = SalesTargetForm
    list_display = ('rep_name', 'month', 'amount')
    list_editable = ('amount',)
    list_filter  = ('manager',)
    date_hierarchy = 'month'

    @admin.display(description='Sales rep', ordering='manager')
    def rep_name(self, obj):
        rep = SalesRep.objects.filter(key=obj.manager).first()
        return rep.name if rep else obj.manager


@admin.register(Promotion)
class PromotionAdmin(ImportExportModelAdmin):
    resource_classes = [PromotionResource]
    list_display  = ('name', 'company', 'start_date', 'end_date', 'status')
    list_filter   = ('company',)
    search_fields = ('name', 'details', 'prizes')


admin.site.site_header = "Retail Management System"
admin.site.site_title = "Retail Management Admin"
admin.site.index_title = "Retail Management Admin"