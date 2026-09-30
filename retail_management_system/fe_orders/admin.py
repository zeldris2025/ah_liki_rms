from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Issue, Order, OrderItem, Product


class ProductResource(resources.ModelResource):
    class Meta:
        model = Product
        import_id_fields = ('name',)
        fields = ('product_no', 'name', 'category', 'unit', 'cost', 'unit_price', 'unit_price_incl_vat',
                  'available', 'quick_link')


@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_classes = [ProductResource]
    list_display  = ('product_no', 'name', 'category', 'unit', 'cost', 'unit_price', 'unit_price_incl_vat', 'available')
    list_filter   = ('category', 'available')
    list_editable = ('unit_price', 'available')
    search_fields = ('product_no', 'name', 'category')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ('product',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = ('number', 'shop', 'placed_by', 'status', 'created_at')
    list_filter   = ('status', 'placed_by')
    search_fields = ('shop__name',)
    raw_id_fields = ('shop',)
    inlines       = [OrderItemInline]


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display  = ('category', 'shop', 'reported_by', 'status', 'created_at')
    list_filter   = ('status', 'category')
    search_fields = ('shop__name', 'description')
    raw_id_fields = ('shop',)
