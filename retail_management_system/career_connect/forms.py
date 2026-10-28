from django import forms

from .models import ExpressionOfInterest


class InterestForm(forms.ModelForm):
    # Left empty by people; bots that fill every field are quietly ignored
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}))
    consent = forms.BooleanField(
        label='I agree that Ah Liki Wholesale may contact me about this role using the details above.')

    class Meta:
        model = ExpressionOfInterest
        fields = ('full_name', 'email', 'phone', 'school', 'message')
        widgets = {
            'full_name': forms.TextInput(attrs={'autocomplete': 'name'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'phone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
            'message': forms.Textarea(attrs={'rows': 4, 'maxlength': 1500}),
        }
        labels = {'message': 'Tell us a little about yourself (optional)'}

    def is_bot(self):
        return bool(self.cleaned_data.get('website'))
