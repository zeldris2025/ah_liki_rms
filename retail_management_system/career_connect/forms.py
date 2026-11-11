from datetime import date, timedelta

from django import forms
from django.utils.text import slugify

from . import i18n
from .models import (ATTACHMENT_TYPES, MAX_ATTACHMENT_MB, Company, Department, Employee, ExpressionOfInterest, Role,
                     office_today, week_label)

ACCEPT = ','.join('.' + t for t in ATTACHMENT_TYPES)
FILE_HELP = f'PDF, Word or a photo, under {MAX_ATTACHMENT_MB} MB.'
QUALIFICATIONS_HELP = 'Certificates or transcripts in one file. ' + FILE_HELP


class ApplicationForm(forms.ModelForm):
    """The application for a general position: every detail is needed except the email (not everyone has one)."""
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
        labels = {'full_name': 'Name', 'email': 'Email (optional)', 'phone': 'Phone number',
                  'highest_qualification': 'Experience (highest qualification)'}

    def __init__(self, *args, lang=i18n.ENGLISH, **kwargs):
        super().__init__(*args, **kwargs)
        self.lang = lang
        for name in ApplicationForm.Meta.fields:
            self.fields[name].required = name != 'email'   # not everyone has an email address

    def _translate(self):
        """Labels, hints and the usual error messages in the applicant's language."""
        if self.lang == i18n.ENGLISH:
            return
        tr = lambda text: i18n.translate(text, self.lang)
        mb = {'mb': MAX_ATTACHMENT_MB}
        hints = {FILE_HELP: i18n.translate('PDF, Word or a photo, under {mb} MB.', self.lang, **mb),
                 QUALIFICATIONS_HELP: i18n.translate(
                     'Certificates or transcripts in one file. PDF, Word or a photo, under {mb} MB.',
                     self.lang, **mb)}
        for field in self.fields.values():
            field.label = tr(field.label)
            if field.help_text:
                field.help_text = hints.get(field.help_text, tr(field.help_text))
            if 'placeholder' in field.widget.attrs:
                field.widget.attrs['placeholder'] = tr(field.widget.attrs['placeholder'])
            field.error_messages = {key: i18n.translate_error(msg, self.lang) for key, msg in field.error_messages.items()}

    def full_clean(self):
        super().full_clean()
        # Messages from validators (file type and size, age limits) arrive already written in English
        if self.lang != i18n.ENGLISH and self._errors:
            for errors in self._errors.values():
                errors.data = [i18n.translate_error(e, self.lang) for e in errors]

    def is_bot(self):
        return bool(self.cleaned_data.get('website'))


class CorporateApplicationForm(ApplicationForm):
    """A corporate position also takes the CV, cover letter and copies of qualifications, all optional."""
    class Meta(ApplicationForm.Meta):
        fields = ApplicationForm.Meta.fields + ('cv', 'cover_letter', 'qualifications_file')
        widgets = {**ApplicationForm.Meta.widgets,
                   **{name: forms.ClearableFileInput(attrs={'accept': ACCEPT})
                      for name in ('cv', 'cover_letter', 'qualifications_file')}}
        labels = {**ApplicationForm.Meta.labels, 'cv': 'CV (optional)', 'cover_letter': 'Cover letter (optional)',
                  'qualifications_file': 'Qualifications (optional)'}
        help_texts = {'cv': FILE_HELP, 'cover_letter': FILE_HELP,
                      'qualifications_file': QUALIFICATIONS_HELP}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('cv', 'cover_letter', 'qualifications_file'):   # all optional: not everyone has them to hand
            self.fields[name].required = False


def application_form(role, *args, **kwargs):
    """The form applicants fill in for this role (pass lang='sm' for Samoan)."""
    form = (CorporateApplicationForm if role.is_corporate else ApplicationForm)(*args, **kwargs)
    form._translate()
    return form


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
        self.fields['employment_type'].required = True
        self.fields['employment_type'].choices = Role.HOURS_CHOICES   # no empty choice: HR pick one
        self.fields['employment_type'].error_messages['required'] = 'Choose full time or part time.'
        for name, field in self.fields.items():
            if name not in ('is_published', 'position_type', 'employment_type'):
                field.widget.attrs['class'] = 'sms-input'

    class Meta:
        model = Role
        # No 'vacancy_status': the required expiry date sets it (currently recruiting until the date is due).
        # No apply button choice either: applicants always apply on the position page, with the form for its type.
        fields = ('position_type', 'employment_type', 'title', 'summary', 'expires_on', 'description', 'jd_file', 'responsibilities',
                  'qualifications', 'skills', 'how_to_apply', 'is_published')
        labels = {'title': 'Position title', 'summary': 'Short summary', 'expires_on': 'Expiry date',
                  'description': 'Job description', 'jd_file': 'Or upload the job description (JD)',
                  'is_published': 'Show on Career Connect', 'employment_type': 'Full time or part time'}
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
            'employment_type': forms.RadioSelect,
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


class TurnoverForm(forms.Form):
    """One company's week: how many employees left and how many employees it has (the % is worked out from them).
    The weeks offered are those of the month on screen. Saving a week that already has figures replaces them."""
    company = forms.ModelChoiceField(Company.objects.all(), empty_label='Choose a company')
    week = forms.TypedChoiceField(coerce=date.fromisoformat, error_messages={'invalid_choice': 'Pick a week.'})
    leavers = forms.IntegerField(label='Number who left', min_value=0, required=False,
                                 widget=forms.NumberInput(attrs={'placeholder': 'e.g. 1', 'inputmode': 'numeric'}),
                                 help_text='Counted from the names above. Type it yourself only if you don’t have '
                                           'every name.')
    employees = forms.IntegerField(label='Number of employees', min_value=1, required=False,
                                   widget=forms.NumberInput(attrs={'placeholder': 'e.g. 66', 'inputmode': 'numeric'}),
                                   help_text='Filled in from the company. Change it only when it changes: '
                                             'the new number is kept for next time.')
    note = forms.CharField(label='Note (optional)', required=False, max_length=200,
                           widget=forms.TextInput(attrs={'placeholder': 'e.g. 1 resigned'}))

    def __init__(self, *args, weeks=(), named=(), **kwargs):
        """weeks: the Mondays HR can pick (the month on screen, up to this week). named: the employees already
        recorded as leaving in the week being edited (to fill in their names)."""
        super().__init__(*args, **kwargs)
        self.named = []   # (employee, left on, reason) once valid
        self.leaver_errors = []
        if self.is_bound:
            d = self.data
            self.leaver_rows = [{'id': i, 'name': n.strip(), 'date': dt, 'reason': r.strip()} for i, n, dt, r in zip(
                d.getlist('leaver_id'), d.getlist('leaver_name'), d.getlist('leaver_date'),
                d.getlist('leaver_reason')) if n.strip()]
        else:
            self.leaver_rows = [{'id': e.pk, 'name': leaver_label(e), 'date': e.left_on.isoformat() if e.left_on else '',
                                 'reason': e.leaving_reason} for e in named]
        self.fields['week'].choices = [(w.isoformat(), f'Week of {week_label(w)}') for w in weeks]
        for field in self.fields.values():
            field.widget.attrs['class'] = 'sms-input'

    def clean(self):
        data = super().clean()
        company = data.get('company')
        if data.get('employees') is None and company:
            data['employees'] = company.employee_count   # the company's kept number
            if data['employees'] is None:
                self.add_error('employees', f'Enter the number of employees at {company.name} once; '
                                            'it is kept for next time.')
        week = data.get('week')
        if company and week:
            self._clean_named(company, week)
        listed = len(self.leaver_rows)
        if data.get('leavers') is None:
            data['leavers'] = listed   # the names listed
        elif data['leavers'] < listed:
            self.add_error('leavers', f'You named {listed} employee{"s" if listed != 1 else ""} who left, so this '
                                      f'can’t be less than {listed}.')
        leavers, employees = data.get('leavers'), data.get('employees')
        if leavers is not None and employees and leavers > employees:
            self.add_error('leavers', 'More employees left than the company has. Check both numbers.')
        return data

    def _clean_named(self, company, week):
        """Matches each name typed in to one of the company's employees, with the date they left (in the week)."""
        today = office_today()
        sunday = week + timedelta(days=6)
        seen = set()
        for row in self.leaver_rows:
            found = find_employee(company, row)
            if isinstance(found, list):
                self.leaver_errors.append(f'There are {len(found)} employees called {row["name"]} at {company.name}: '
                                          f'pick the right one from the suggestions.')
                continue
            if found is None:
                self.leaver_errors.append(f'{row["name"]} isn’t on the Employees list for {company.name}. Pick a name '
                                          f'from the suggestions, or add them on the Employees page first.')
                continue
            row['id'], row['name'] = found.pk, leaver_label(found)
            if found.pk in seen:
                self.leaver_errors.append(f'{found.full_name} is listed twice.')
                continue
            seen.add(found.pk)
            t = found.turnover
            if t is not None and (t.company_id, t.week) != (company.pk, week):
                self.leaver_errors.append(f'{found.full_name} is already counted as leaving in the week of '
                                          f'{t.week_label}. Remove them from that week first.')
                continue
            if row['date']:
                left_on = parse_day(row['date'])
                if left_on is None or not week <= left_on <= sunday:
                    self.leaver_errors.append(f'{found.full_name}: the date they left must be in the week of '
                                              f'{week_label(week)}.')
                    continue
                if left_on > today:
                    self.leaver_errors.append(f'{found.full_name}: the date they left can’t be after today.')
                    continue
            else:   # no date given: the end of the week (or today, for this week)
                left_on = min(sunday, today)
            row['date'] = left_on.isoformat()
            self.named.append((found, left_on, row['reason'][:200]))
        for message in self.leaver_errors:
            self.add_error(None, message)


def leaver_label(e):
    """How an employee shows in the name suggestions: 'Jane Doe · Cashier · #E12'."""
    return ' · '.join(p for p in (e.full_name, e.position, f'#{e.employee_id}' if e.employee_id else '') if p)


def parse_day(text):
    """A date typed as 2026-11-03 or 3/11/2026 (day first), else None."""
    text = (text or '').strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        d, m, y = (int(x) for x in text.replace('-', '/').replace('.', '/').split('/'))
        return date(y + 2000 if y < 100 else y, m, d)
    except (ValueError, TypeError):
        return None


def find_employee(company, row):
    """The company's employee a typed-in row names: by the suggestion picked, else by their exact name. A list when
    several share the name, None when nobody has it."""
    people = Employee.objects.filter(company=company).select_related('turnover')
    if str(row['id']).isdigit():
        found = people.filter(pk=int(row['id'])).first()
        if found and row['name'] in (leaver_label(found), found.full_name):
            return found
    name = ' '.join(row['name'].split(' · ')[0].split()).lower()
    matches = [e for e in people if ' '.join(e.full_name.split()).lower() == name]
    if len(matches) == 1:
        return matches[0]
    return matches or None


def _date_input():
    return forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ('company', 'employee_id', 'first_name', 'last_name', 'department', 'position', 'email', 'phone',
                  'start_date', 'status', 'left_on', 'leaving_reason', 'notes')
        widgets = {'start_date': _date_input(), 'left_on': _date_input(),
                   'notes': forms.Textarea(attrs={'rows': 3}),
                   'department': forms.TextInput(attrs={'list': 'em-departments', 'autocomplete': 'off'}),
                   'position': forms.TextInput(attrs={'list': 'em-positions', 'autocomplete': 'off'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company'].empty_label = 'Choose a company'
        for field in self.fields.values():
            field.widget.attrs['class'] = 'sms-input'

    def clean(self):
        data = super().clean()
        if data.get('status') == Employee.LEFT:
            if not data.get('left_on'):
                self.add_error('left_on', 'Enter the date they left.')
            elif data['left_on'] > office_today():
                self.add_error('left_on', 'This date can’t be after today.')
        return data


class EmployeeFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'placeholder': 'Search name, ID, position…', 'type': 'search'}))
    company = forms.ModelChoiceField(Company.objects.all(), required=False, empty_label='All companies',
                                     to_field_name='slug')
    department = forms.ChoiceField(required=False)
    status = forms.ChoiceField(required=False, choices=[('', 'Active and left')] + Employee.STATUSES)
    left_from = forms.DateField(required=False, label='Left from', widget=_date_input())
    left_to = forms.DateField(required=False, label='Left to', widget=_date_input())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        departments = (Employee.objects.exclude(department='').order_by('department')
                       .values_list('department', flat=True).distinct())
        self.fields['department'].choices = [('', 'All departments')] + [(d, d) for d in departments]
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'sms-input'
            field.widget.attrs.setdefault('aria-label', field.label or name.title())
