from django.urls import path
from . import views

urlpatterns = [
    # FE screens (url names starting with fe_ are open to the fe_boys group)
    path('fe/',                               views.fe_home,          name='fe_home'),
    path('fe/order/',                         views.fe_place_order,   name='fe_place_order'),
    path('fe/orders/',                        views.fe_order_list,    name='fe_order_list'),
    path('fe/orders/<int:order_id>/',         views.fe_order_detail,  name='fe_order_detail'),
    path('orders/sales-export/',              views.sales_export_download, name='sales_export'),   # office only
    path('fe/issues/',                        views.fe_issue_list,    name='fe_issue_list'),
    path('fe/issues/new/',                    views.fe_report_issue,  name='fe_report_issue'),
    path('fe/issues/<int:issue_id>/status/',  views.fe_issue_status,  name='fe_issue_status'),

    # Office: product catalogue
    path('products/',                         views.product_list,     name='product_list'),
    path('products/add/',                     views.product_form,     name='product_add'),
    path('products/<int:product_id>/edit/',   views.product_form,     name='product_edit'),
    path('products/<int:product_id>/toggle/', views.product_toggle,   name='product_toggle'),
    path('products/<int:product_id>/delete/', views.product_delete,   name='product_delete'),
    path('products/import/',                  views.product_import,   name='product_import'),
    path('products/template/',                views.product_template, name='product_template'),
    path('products/export/',                  views.product_export,   name='product_export'),
]
