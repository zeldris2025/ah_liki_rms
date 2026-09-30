from django.urls import path
from . import views

urlpatterns = [
    path('',                                views.atlas,         name='atlas'),
    path('shops/<int:shop_id>/location/',   views.shop_location, name='atlas_shop_location'),
]
