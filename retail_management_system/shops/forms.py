from django import forms
from tablib import Dataset
from .models import Shop, Business, Sponsorship, Survey, SurveyResponse


class CSVImportForm(forms.Form):
    """Base form for importing CSV data."""
    csv_file = forms.FileField(
        label='CSV File',
        help_text='Upload a CSV file with the appropriate columns',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )


class ShopCSVImportForm(CSVImportForm):
    """Form for importing shops from CSV."""
    pass


class BusinessCSVImportForm(CSVImportForm):
    """Form for importing HORECA businesses from CSV."""
    pass


class SponsorshipCSVImportForm(CSVImportForm):
    """Form for importing sponsorships from CSV."""
    pass


class SurveyForm(forms.ModelForm):
    """Form for creating/editing surveys."""
    class Meta:
        model = Survey
        fields = ['title', 'category', 'description', 'location', 'region', 'period']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Survey title'}),
            'category': forms.Select(attrs={'class': 'sms-input'}),
            'description': forms.Textarea(attrs={'class': 'sms-input', 'rows': 3, 'placeholder': 'Optional description'}),
            'location': forms.Select(attrs={'class': 'sms-input'}),
            'region': forms.Select(attrs={'class': 'sms-input'}),
            'period': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'e.g., May-26, Q2 2026'}),
        }


class SurveyResponseForm(forms.ModelForm):
    """Form for adding individual survey responses."""
    class Meta:
        model = SurveyResponse
        fields = ['product', 'customer', 'period', 'price', 'quantity', 'location', 'region', 'recorded_by']
        widgets = {
            'product': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Product name'}),
            'customer': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Customer/Shop name'}),
            'period': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'e.g. May-26'}),
            'location': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Location'}),
            'region': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Region'}),
            'price': forms.NumberInput(attrs={'class': 'sms-input', 'placeholder': 'Price (WST)', 'step': '0.01'}),
            'quantity': forms.NumberInput(attrs={'class': 'sms-input', 'placeholder': 'Quantity', 'min': '0'}),
            'recorded_by': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Your name'}),
        }


class BulkSurveyResponseForm(forms.Form):
    """Form for bulk CSV import of survey responses."""
    csv_file = forms.FileField(
        label='Upload Survey Data (CSV)',
        help_text='Columns: Products, Customer/Shop, Period, Price, QTY, Location, Region',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )


class SurveyCSVImportForm(BulkSurveyResponseForm):
    """CSV import from the Surveys list: add to an existing survey or create a new one."""
    survey = forms.ModelChoiceField(
        queryset=Survey.objects.order_by('-created_at'), required=False,
        empty_label='— Create a new survey —',
        widget=forms.Select(attrs={'class': 'sms-input'}),
    )
    new_title = forms.CharField(max_length=255, required=False,
                                widget=forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'e.g. Soda prices — May 2026'}))
    new_category = forms.ChoiceField(choices=Survey.CATEGORY_CHOICES, required=False,
                                     widget=forms.Select(attrs={'class': 'sms-input'}))

    field_order = ['survey', 'new_title', 'new_category', 'csv_file']

    def clean(self):
        data = super().clean()
        if not data.get('survey') and not data.get('new_title', '').strip():
            self.add_error('new_title', 'Pick an existing survey or give the new survey a title.')
        return data
