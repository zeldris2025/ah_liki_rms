from django import forms
from django.utils.text import slugify

from .models import ATTACHMENT_TYPES, MAX_ATTACHMENT_MB, Company, Department, ExpressionOfInterest, Role, office_today

ACCEPT = ','.join('.' + t for t in ATTACHMENT_TYPES)
FILE_HELP = f'PDF, Word or a photo, under {MAX_ATTACHMENT_MB} MB.'


class ApplicationForm(forms.ModelForm):
    """The application for a general position: every detail is needed."""
    # Left empty by people; bots that fill every field are quietly ignored
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}))
    consent = forms.BooleanField(
        label='I agree that Ah Liki may contact me about this position using the details above.')

    class Meta:
        model = ExpressionOfInterest
        fields = ('full_name', 'age', 'village', 'email', 'phone', 'highest_qualification')
        widgets = {
            'full_name': forms.TextInput(attrs={'autocomplete': 'name'}),
            'age': forms.NumberInput(attrs={'min': 14, 'max': 99, 'inputmode': 'numeric', 'style': 'max-width:120px'}),
            'village': forms.TextInput(attrs={'autocomplete': 'address-level2'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'phone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
            'highest_qualification': forms.TextInput(attrs={'placeholder': 'e.g. Year 13 certificate, or 2 years in retail'}),
        }
        labels = {'full_name': 'Name', 'phone': 'Phone number',
                  'highest_qualification': 'Experience (highest qualification)'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ApplicationForm.Meta.fields:
            self.fields[name].required = True

    def is_bot(self):
        return bool(self.cleaned_data.get('website'))


class CorporateApplicationForm(ApplicationForm):
    """A corporate position also asks for the CV and cover letter, and copies of qualifications if there are any."""
    class Meta(ApplicationForm.Meta):
        fields = ApplicationForm.Meta.fields + ('cv', 'cover_letter', 'qualifications_file')
        widgets = {**ApplicationForm.Meta.widgets,
                   **{name: forms.ClearableFileInput(attrs={'accept': ACCEPT})
                      for name in ('cv', 'cover_letter', 'qualifications_file')}}
        labels = {**ApplicationForm.Meta.labels, 'cv': 'CV', 'cover_letter': 'Cover letter',
                  'qualifications_file': 'Qualifications (certificates)'}
        help_texts = {'cv': FILE_HELP, 'cover_letter': FILE_HELP,
                      'qualifications_file': 'Optional: certificates or transcripts in one file. ' + FILE_HELP}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cv'].required = self.fields['cover_letter'].required = True


def application_form(role, *args, **kwargs):
    """The form applicants fill in for this role."""
    return (CorporateApplicationForm if role.is_corporate else ApplicationForm)(*args, **kwargs)


class VacancyForm(forms.ModelForm):
    """What HR fills in for a vacancy. The web address is made from the title and kept when the title changes."""
    # 'c<id>' = straight on the company page (companies without departments), 'd<id>' = in that department
    place = forms.ChoiceField(label='Company and department',
                              help_text='Pick "No department" for a company without departments: the position is '
                                        'listed on the company page.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Departments grouped under their company, so the same name in two companies can't be confused
        groups = {c: [(f'c{c.pk}', 'No department (company page)')] for c in Company.objects.all()}
        for d in Department.objects.select_related('company'):
            groups[d.company].append((f'd{d.pk}', d.name))
        self.fields['place'].choices = [('', 'Choose a company and department…'),
                                        *((c.name, options) for c, options in groups.items())]
        if self.instance.pk:
            r = self.instance
            self.initial['place'] = f'd{r.department_id}' if r.department_id else f'c{r.company_id}'
        self.fields['expires_on'].required = True
        self.fields['expires_on'].help_text = ('Shown as currently recruiting until this date; on the date it comes off '
                                               'Career Connect automatically.')
        for name, field in self.fields.items():
            if name not in ('is_published', 'position_type'):
                field.widget.attrs['class'] = 'sms-input'

    class Meta:
        model = Role
        # No 'vacancy_status': the required expiry date sets it (currently recruiting until the date is due).
        # No apply button choice either: applicants always apply on the position page, with the form for its type.
        fields = ('position_type', 'title', 'summary', 'expires_on', 'description', 'jd_file', 'responsibilities',
                  'qualifications', 'skills', 'how_to_apply', 'is_published')
        labels = {'title': 'Position title', 'summary': 'Short summary', 'expires_on': 'Expiry date',
                  'description': 'Job description', 'jd_file': 'Or upload the job description (JD)',
                  'is_published': 'Show on Career Connect'}
        help_texts = {'summary': 'One line shown under the title on the department or company page.',
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
            'expires_on': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'description': forms.Textarea(attrs={'rows': 5}),
            'jd_file': forms.ClearableFileInput(attrs={'accept': '.pdf,.doc,.docx'}),
            'position_type': forms.RadioSelect,
        }

    def clean_expires_on(self):
        date = self.cleaned_data.get('expires_on')
        if date and 'expires_on' in self.changed_data and date <= office_today():
            raise forms.ValidationError('Choose a date after today (the position comes off Career Connect on this date).')
        return date

    field_order = ('place',)

    def clean_place(self):
        value = self.cleaned_data['place']
        model = Department if value.startswith('d') else Company
        try:
            return model.objects.get(pk=int(value[1:]))
        except (ValueError, model.DoesNotExist):
            raise forms.ValidationError('Choose a company and department.')

    def clean(self):
        data = super().clean()
        place = data.get('place')
        if isinstance(place, Department):
            self.instance.company, self.instance.department = place.company, place
        elif isinstance(place, Company):
            self.instance.company, self.instance.department = place, None
        if data.get('position_type') == Role.GENERAL:   # the role details are for corporate positions only
            for name in ('responsibilities', 'qualifications', 'skills'):
                data[name] = ''
        return data

    def save(self, commit=True):
        role = super().save(commit=False)
        role.apply_method = Role.APPLY_FORM
        if not role.slug or 'place' in self.changed_data:
            role.slug = self._free_slug(role)
        if commit:
            role.save()
        return role

    def _free_slug(self, role):
        base = slugify(role.title)[:70] or 'position'
        siblings = (Role.objects.filter(department=role.department) if role.department
                    else Role.objects.filter(company=role.company, department__isnull=True))
        taken = set(siblings.exclude(pk=role.pk).values_list('slug', flat=True))
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
                               + [('draft', 'Hidden (drafts)'), ('expired', 'Expired')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'sms-input'
