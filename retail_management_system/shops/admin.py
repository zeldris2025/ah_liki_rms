from django.contrib import admin
from django.utils.html import format_html
from .models import Shop, ShopPhoto, Business, BusinessPhoto, Sponsorship, SponsorshipPhoto


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
class ShopAdmin(admin.ModelAdmin):
    inlines = [ShopPhotoInline]
    list_display  = ('name', 'owner', 'phone', 'island', 'region', 'tip_top', 'photo_count')
    list_filter   = ('island', 'region', 'tip_top')
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
class BusinessAdmin(admin.ModelAdmin):
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
class SponsorshipAdmin(admin.ModelAdmin):
    inlines = [SponsorshipPhotoInline]
    list_display  = ('customer', 'type', 'value', 'status', 'start', 'end', 'photo_count')
    list_filter   = ('status', 'type')
    search_fields = ('customer', 'notes')

    def photo_count(self, obj):
        return obj.photos.count()
    photo_count.short_description = "Photos"
