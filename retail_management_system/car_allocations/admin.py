from django.contrib import admin

from .models import Booking, Notification


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('car', 'start', 'end', 'reason', 'booked_by', 'status', 'decided_by', 'email_status')
    list_filter = ('status', 'car')
    search_fields = ('reason', 'booked_by__username', 'booked_by__first_name', 'booked_by__last_name')
    date_hierarchy = 'start'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'message', 'created_at', 'read')
    list_filter = ('read',)
