from django.urls import path

from . import views

# Every name here is listed in access.AJ_URL_NAMES
urlpatterns = [
    path('product-qty-sales/',           views.product_qty, name='aj_product_qty'),
    path('product-qty-sales/analytics/', views.analytics,   name='aj_analytics'),
    path('product-qty-sales/import/',    views.import_csv,  name='aj_import'),
    path('product-qty-sales/template/',  views.download_template, name='aj_template'),
    path('product-qty-sales/pin/',       views.pin,         name='aj_pin'),
    path('product-qty-sales/targets/',   views.targets,     name='aj_targets'),
    path('product-qty-sales/groups/add/',            views.group_form, name='aj_group_add'),
    path('product-qty-sales/groups/<int:group_id>/', views.group_form, name='aj_group_edit'),
]
