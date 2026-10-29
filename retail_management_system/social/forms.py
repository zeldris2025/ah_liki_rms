from django import forms

from .models import COMPANIES, PLATFORMS, is_update_day, office_today


class SocialUpdateForm(forms.Form):
    """One update day's numbers for every company at once: a Facebook and an Instagram box per company.
    A box left empty stays empty; clearing both of a company's boxes removes that company's numbers for the day."""
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'sms-input'}),
                           help_text='A Monday or a Saturday')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, _ in COMPANIES:
            for platform, label in PLATFORMS:
                self.fields[f'{key}_{platform}'] = forms.IntegerField(
                    label=label, required=False, min_value=0,
                    widget=forms.NumberInput(attrs={'class': 'sms-input', 'min': 0, 'inputmode': 'numeric',
                                                    'placeholder': '—'}))

    def clean_date(self):
        day = self.cleaned_data['date']
        if not is_update_day(day):
            raise forms.ValidationError(f'{day:%A} isn’t an update day. Social numbers are updated on Mondays and Saturdays.')
        if day > office_today():
            raise forms.ValidationError('That day hasn’t come yet.')
        return day

    def rows(self):
        """(company key, name, facebook box, instagram box) for the template."""
        return [(key, name, self[f'{key}_facebook'], self[f'{key}_instagram']) for key, name in COMPANIES]

    def numbers(self):
        """{company key: {'facebook': n or None, 'instagram': n or None}} from the cleaned boxes."""
        return {key: {p: self.cleaned_data.get(f'{key}_{p}') for p, _ in PLATFORMS} for key, _ in COMPANIES}
