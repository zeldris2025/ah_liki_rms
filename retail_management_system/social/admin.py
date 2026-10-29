from django.contrib import admin

from .models import SocialCount


@admin.register(SocialCount)
class SocialCountAdmin(admin.ModelAdmin):
    list_display = ('date', 'company', 'facebook', 'instagram', 'updated_by', 'updated_at')
    list_filter = ('company',)
    date_hierarchy = 'date'
