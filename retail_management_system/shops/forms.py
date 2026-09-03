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


class SalesCSVImportForm(CSVImportForm):
    """Form for importing shop sales from CSV."""
    csv_file = forms.FileField(
        label='Sales CSV File',
        help_text='Columns: products, quantity, total_sales, date (YYYY-MM-DD)',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )


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
        fields = ['product', 'category', 'customer', 'location', 'region', 'week', 'price', 'quantity', 'rating', 'notes', 'recorded_by']
        widgets = {
            'product': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Product name'}),
            'category': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'e.g., SODA, SNACKS'}),
            'customer': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Customer/Store name'}),
            'location': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Location'}),
            'region': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Region'}),
            'week': forms.NumberInput(attrs={'class': 'sms-input', 'placeholder': 'Week number', 'min': '1', 'max': '52'}),
            'price': forms.NumberInput(attrs={'class': 'sms-input', 'placeholder': 'Price (WST)', 'step': '0.01'}),
            'quantity': forms.NumberInput(attrs={'class': 'sms-input', 'placeholder': 'Quantity', 'min': '0'}),
            'rating': forms.Select(attrs={'class': 'sms-input'}, choices=[(i, f'{i} Stars') for i in range(1, 6)]),
            'notes': forms.Textarea(attrs={'class': 'sms-input', 'rows': 2, 'placeholder': 'Additional notes'}),
            'recorded_by': forms.TextInput(attrs={'class': 'sms-input', 'placeholder': 'Your name'}),
        }


class BulkSurveyResponseForm(forms.Form):
    """Form for bulk CSV import of survey responses."""
    csv_file = forms.FileField(
        label='Upload Survey Data (CSV)',
        help_text='Columns: product, category, customer, location, region, week, price, quantity, rating, notes',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )
