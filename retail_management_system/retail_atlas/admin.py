from django import forms
from django.contrib import admin

from .models import CompanyLocation, ShopLocation

LEAFLET = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/'


class MapPickerAdmin(admin.ModelAdmin):
    """Shows a map under the form: click it (or drag the pin) to fill in Latitude and Longitude."""
    change_form_template = 'admin/retail_atlas/map_change_form.html'

    class Media:
        css = {'all': (LEAFLET + 'leaflet.css',)}
        js = (LEAFLET + 'leaflet.js',)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user.get_username()
        super().save_model(request, obj, form, change)


@admin.register(ShopLocation)
class ShopLocationAdmin(MapPickerAdmin):
    list_display  = ('shop', 'latitude', 'longitude', 'updated_by', 'updated_at')
    search_fields = ('shop__name', 'shop__address')
    autocomplete_fields = ('shop',)
    fields = ('shop', ('latitude', 'longitude'))


class CompanyLocationForm(forms.ModelForm):
    class Meta:
        model = CompanyLocation
        fields = '__all__'
        widgets = {'company': forms.TextInput(attrs={'list': 'company-names', 'autocomplete': 'off'})}


@admin.register(CompanyLocation)
class CompanyLocationAdmin(MapPickerAdmin):
    form = CompanyLocationForm
    list_display  = ('name', 'company', 'kind', 'address', 'is_published', 'updated_by', 'updated_at')
    list_filter   = ('company', 'kind', 'is_published')
    list_editable = ('is_published',)
    search_fields = ('name', 'company', 'address')
    fieldsets = (
        (None, {'fields': ('company', 'name', 'kind', 'is_published')}),
        ('Details shown on the map', {'fields': ('address', 'phone', 'notes')}),
        ('Where it is', {'fields': (('latitude', 'longitude'),),
                         'description': 'Click the map below to place the site, or drag its pin. '
                                        'Switch to Satellite to see the buildings.'}),
    )

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Suggestions for the Company box: companies already used here, on Career Connect and in Social #s
        from career_connect.models import Company
        from social.models import COMPANIES
        names = set(CompanyLocation.objects.values_list('company', flat=True))
        names |= set(Company.objects.values_list('name', flat=True)) | {n for _, n in COMPANIES}
        extra_context = {**(extra_context or {}), 'company_names': sorted(names, key=str.lower)}
        return super().changeform_view(request, object_id, form_url, extra_context)
