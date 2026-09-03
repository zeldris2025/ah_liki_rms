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
    path('shops/<int:shop_id>/import-sales/', views.import_shop_sales,  name='import_shop_sales'),

    # Island / region filtered views
    path('territory/<str:territory>/',       views.territory_shops,     name='territory_shops'),
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

    # CSV Import
    path('import/shops/',                     views.import_shops,       name='import_shops'),
    path('import/businesses/',                views.import_businesses,  name='import_businesses'),
    path('import/sponsorships/',              views.import_sponsorships,name='import_sponsorships'),

    # CSV Templates Download
    path('templates/shops/',                  views.download_shop_template,        name='download_shop_template'),
    path('templates/businesses/',             views.download_business_template,    name='download_business_template'),
    path('templates/sponsorships/',           views.download_sponsorship_template, name='download_sponsorship_template'),
    path('templates/survey-responses/',       views.download_survey_template,      name='download_survey_template'),
    path('templates/sales/',                  views.download_sales_template,       name='download_sales_template'),

    # Surveys
    path('surveys/',                          views.survey_list,            name='survey_list'),
    path('surveys/add/',                      views.add_survey,             name='add_survey'),
    path('surveys/<int:survey_id>/',          views.survey_detail,          name='survey_detail'),
    path('surveys/<int:survey_id>/edit/',     views.edit_survey,            name='edit_survey'),
    path('surveys/<int:survey_id>/delete/',   views.delete_survey,          name='delete_survey'),
    path('surveys/<int:survey_id>/analyze/',  views.survey_analysis,        name='survey_analysis'),
    path('surveys/<int:survey_id>/add-response/',    views.add_survey_response,   name='add_survey_response'),
    path('surveys/<int:survey_id>/import/',   views.import_survey_responses, name='import_survey_responses'),
    path('survey-responses/<int:response_id>/edit/',   views.edit_survey_response,   name='edit_survey_response'),
    path('survey-responses/<int:response_id>/delete/', views.delete_survey_response, name='delete_survey_response'),
]
