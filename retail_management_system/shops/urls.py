from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/',                            views.user_login,         name='login'),
    path('logout/',                           views.user_logout,        name='logout'),

    # Dashboard
    path('',                                  views.dashboard,          name='dashboard'),

    # Shops
    path('shops/',                            views.shop_list,          name='shop_list'),
    path('shops/add/',                        views.add_shop,           name='add_shop'),
    path('shops/<int:shop_id>/',              views.shop_detail,        name='shop_detail'),
    path('shops/<int:shop_id>/edit/',         views.edit_shop,          name='edit_shop'),
    path('shops/<int:shop_id>/delete/',       views.delete_shop,        name='delete_shop'),

    # Island / region filtered views
    path('upolu/<str:region>/',              views.upolu_shops,         name='upolu_shops'),
    path('savaii/<str:region>/',             views.savaii_shops,        name='savaii_shops'),

    # HORECCA
    path('horecca/',                          views.business_list,      name='business_list'),
    path('horecca/add/',                      views.add_business,       name='add_business'),
    path('horecca/<int:biz_id>/edit/',        views.edit_business,      name='edit_business'),
    path('horecca/<int:biz_id>/delete/',      views.delete_business,    name='delete_business'),

    # Sponsorships
    path('sponsorships/',                     views.sponsorship_list,   name='sponsorship_list'),
    path('sponsorships/add/',                 views.add_sponsorship,    name='add_sponsorship'),
    path('sponsorships/<int:sp_id>/edit/',    views.edit_sponsorship,   name='edit_sponsorship'),
    path('sponsorships/<int:sp_id>/delete/',  views.delete_sponsorship, name='delete_sponsorship'),

    # Reports & Download
    path('reports/',                          views.reports,            name='reports'),
    path('reports/download/',                 views.download_report,    name='download_report'),
]
