from django.contrib import admin

from .models import ShopLocation


@admin.register(ShopLocation)
class ShopLocationAdmin(admin.ModelAdmin):
    list_display  = ('shop', 'latitude', 'longitude', 'updated_by', 'updated_at')
    search_fields = ('shop__name', 'shop__address')
    raw_id_fields = ('shop',)
