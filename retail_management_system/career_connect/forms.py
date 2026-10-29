from django import forms
from django.utils.text import slugify

from .models import Company, Department, ExpressionOfInterest, Role


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


class VacancyForm(forms.ModelForm):
    """What HR fills in for a vacancy. The web address is made from the title and kept when the title changes."""
    department = forms.ModelChoiceField(Department.objects.select_related('company'), label='Company and department')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Departments grouped under their company, so the same name in two companies can't be confused
        groups = {}
        for d in self.fields['department'].queryset:
            groups.setdefault(d.company.name, []).append((d.pk, d.name))
        self.fields['department'].choices = [('', 'Choose a company and department…'), *groups.items()]
        for name, field in self.fields.items():
            if name != 'is_published':
                field.widget.attrs['class'] = 'sms-input'

    class Meta:
        model = Role
        # No 'description': the public page never shows it (students email HR for the job description)
        fields = ('department', 'title', 'summary', 'vacancy_status', 'responsibilities',
                  'qualifications', 'skills', 'apply_method', 'apply_email', 'apply_url', 'how_to_apply',
                  'is_published')
        labels = {'title': 'Position title', 'summary': 'Short summary', 'vacancy_status': 'Recruiting status',
                  'is_published': 'Show on Career Connect'}
        help_texts = {'summary': 'One line shown under the title on the department page.',
                      'is_published': "Untick to keep it as a draft that students can't see."}
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Accounts Assistant'}),
            'summary': forms.TextInput(attrs={'placeholder': 'e.g. Support the finance team with daily bookkeeping'}),
            'responsibilities': forms.Textarea(attrs={'rows': 4, 'placeholder': 'One per line'}),
            'qualifications': forms.Textarea(attrs={'rows': 4, 'placeholder': 'One per line'}),
            'skills': forms.Textarea(attrs={'rows': 3, 'placeholder': 'One per line'}),
            'how_to_apply': forms.Textarea(attrs={'rows': 3}),
            'apply_email': forms.EmailInput(attrs={'placeholder': 'e.g. hr@ahliki.com'}),
            'apply_url': forms.URLInput(attrs={'placeholder': 'https://'}),
        }

    def clean(self):
        data = super().clean()
        method = data.get('apply_method')
        if method == Role.APPLY_EMAIL and not data.get('apply_email'):
            self.add_error('apply_email', 'Enter the email address applications should go to.')
        if method == Role.APPLY_LINK and not data.get('apply_url'):
            self.add_error('apply_url', 'Enter the application link.')
        return data

    def save(self, commit=True):
        role = super().save(commit=False)
        if not role.slug or 'department' in self.changed_data:
            role.slug = self._free_slug(role)
        if commit:
            role.save()
        return role

    def _free_slug(self, role):
        base = slugify(role.title)[:70] or 'position'
        taken = set(Role.objects.filter(department=role.department).exclude(pk=role.pk).values_list('slug', flat=True))
        slug, n = base, 2
        while slug in taken:
            slug, n = f'{base}-{n}', n + 1
        return slug


class VacancyFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Search positions…',
                                                                      'type': 'search'}))
    company = forms.ModelChoiceField(Company.objects.all(), required=False, empty_label='All companies',
                                     to_field_name='slug')
    status = forms.ChoiceField(required=False, choices=[('', 'Any status')] + Role.VACANCY_CHOICES
                               + [('draft', 'Hidden (drafts)')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'sms-input'
