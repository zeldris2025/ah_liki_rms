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
    path('territory/<str:territory>/',       views.territory_shops,     name='territory_shops'),
    path('upolu/<str:region>/',              views.upolu_shops,         name='upolu_shops'),
    path('savaii/<str:region>/',             views.savaii_shops,        name='savaii_shops'),

    # HORECCA
    path('corporate-sales/',                  views.corporate_sales,    name='corporate_sales'),
    path('corporate-sales/targets/',          views.corporate_targets,  name='corporate_targets'),
    path('corporate-sales/<str:manager>/',    views.corporate_manager,  name='corporate_manager'),
    path('horecca/',                          views.business_list,      name='business_list'),
    path('horecca/add/',                      views.add_business,       name='add_business'),
    path('horecca/<int:biz_id>/edit/',        views.edit_business,      name='edit_business'),
    path('horecca/<int:biz_id>/delete/',      views.delete_business,    name='delete_business'),

    # Promotions
    path('promotions/',                       views.promotion_list,     name='promotion_list'),
    path('promotions/add/',                   views.promotion_form,     name='add_promotion'),
    path('promotions/<int:promo_id>/edit/',   views.promotion_form,     name='edit_promotion'),

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
    path('import/monthly-sales/',             views.import_monthly_sales, name='import_monthly_sales'),
    path('sales/',                            views.monthly_sales_list,  name='monthly_sales'),
    path('product-sales/',                    views.product_sales_page,  name='product_sales'),
    path('product-sales/pin/',                views.product_sales_pin,   name='product_sales_pin'),
    path('product-sales/targets/',            views.quick_link_targets,  name='quick_link_targets'),
    path('product-sales/groups/new/',         views.product_group_form,  name='product_group_add'),
    path('product-sales/groups/<int:group_id>/', views.product_group_form, name='product_group_edit'),
    path('product-sales/export/',             views.product_sales_export, name='product_sales_export'),
    path('import/product-sales/',             views.import_product_sales, name='import_product_sales'),
    path('import/customer-product-sales/',    views.import_customer_product_sales, name='import_customer_product_sales'),
    path('templates/customer-product-sales/', views.download_customer_product_sales_template, name='download_customer_product_sales_template'),
    path('templates/product-sales/',          views.download_product_sales_template, name='download_product_sales_template'),
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
    path('surveys/import/',                   views.import_surveys,         name='import_surveys'),
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
