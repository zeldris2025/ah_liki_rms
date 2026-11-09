from django.contrib import admin

from shops.admin import FastDeleteMixin, MonthFilter, YearFilter

from .models import QtyPinnedProduct, QtyProductGroup, QtySales, QtyTarget


@admin.register(QtySales)
class QtySalesAdmin(FastDeleteMixin, admin.ModelAdmin):
    """Filter by year or month, tick the box at the top, click "Select all", then "Delete selected": thousands of
    rows go in one query (see shops.admin.fast_delete)."""
    list_display = ('month', 'product_code', 'product_name', 'qty', 'updated_at')
    list_filter = (YearFilter, MonthFilter)
    search_fields = ('product_code', 'product_name')
    date_hierarchy = 'month'
    list_per_page = 100


@admin.register(QtyProductGroup)
class QtyProductGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'keywords', 'created_at')
    search_fields = ('name', 'keywords', 'product_codes')


@admin.register(QtyPinnedProduct)
class QtyPinnedProductAdmin(admin.ModelAdmin):
    list_display = ('product_code', 'pinned_at')


@admin.register(QtyTarget)
class QtyTargetAdmin(admin.ModelAdmin):
    list_display = ('month', 'group', 'product_code', 'qty')
    list_filter = ('group',)
    date_hierarchy = 'month'
