from django.urls import path

from . import views

# Every name here is listed in access.SOCIAL_URL_NAMES
urlpatterns = [
    path('social/',            views.numbers,   name='social_numbers'),
    path('social/update/',     views.update,    name='social_update'),
    path('social/import/',     views.import_csv, name='social_import'),
    path('social/template/',   views.download_template, name='social_template'),
    path('social/analytics/',  views.analytics, name='social_analytics'),
]
