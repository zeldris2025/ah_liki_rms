from django.urls import path

from . import views

urlpatterns = [
    path('car-allocations/',                         views.car_allocations,    name='car_allocations'),
    path('car-allocations/bookings/',                views.car_bookings,       name='car_bookings'),
    path('car-allocations/search/',                  views.car_booking_search, name='car_booking_search'),
    path('car-allocations/book/',                    views.car_book,           name='car_book'),
    path('car-allocations/<int:booking_id>/edit/',   views.car_booking_edit,   name='car_booking_edit'),
    path('car-allocations/<int:booking_id>/cancel/', views.car_booking_cancel, name='car_booking_cancel'),
    path('notifications/',                           views.notifications,      name='notifications'),
    path('notifications/read/',                      views.notifications_read, name='notifications_read'),
]
