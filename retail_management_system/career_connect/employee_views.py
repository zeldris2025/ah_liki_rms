"""HR Employees: everyone who works (or worked) at each company in the group.

HR add, edit and remove employees, filter the list, and move it in and out of the SMS as a CSV file. Naming an
employee on the Staff turnover page marks them as left (see hr_views.turnover).
"""
import csv
import io

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import EmployeeFilterForm, EmployeeForm, parse_day
from .hr_views import SERIES, hr_page
from .models import Company, Employee, office_today

PER_PAGE = 25
MAX_IMPORT_MB = 5
# The CSV columns, in order (the export writes them, the import reads them by name)
COLUMNS = [('employee_id', 'Employee ID'), ('first_name', 'First name'), ('last_name', 'Last name'),
           ('company', 'Company'), ('department', 'Department'), ('position', 'Position'), ('email', 'Email'),
           ('phone', 'Phone'), ('start_date', 'Started on'), ('status', 'Status'), ('left_on', 'Left on'),
           ('leaving_reason', 'Reason for leaving'), ('notes', 'Notes')]


def _filtered(request):
    """The filter form, and the employees it picks out (the date range picks people who left in it)."""
    filters = EmployeeFilterForm(request.GET or None)
    people = Employee.objects.select_related('company', 'turnover')
    f = filters.cleaned_data if filters.is_valid() else {}
    if f.get('q'):
        for word in f['q'].split():
            people = people.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word) |
                                   Q(employee_id__icontains=word) | Q(position__icontains=word) |
                                   Q(department__icontains=word) | Q(email__icontains=word))
    if f.get('department'):
        people = people.filter(department=f['department'])
    left = Q(status=Employee.LEFT)
    if f.get('left_from'):
        left &= Q(left_on__gte=f['left_from'])
    if f.get('left_to'):
        left &= Q(left_on__lte=f['left_to'])
    return filters, f, people, left


@hr_page
def employees(request):
    filters, f, people, left = _filtered(request)
    dated = bool(f.get('left_from') or f.get('left_to'))
    # The cards: active and left for every company (the search and department filters apply)
    counts = {row['company']: row for row in people.values('company').annotate(
        active=Count('pk', filter=Q(status=Employee.ACTIVE)), left=Count('pk', filter=left))}
    company = f.get('company')
    cards = []
    for i, c in enumerate(Company.objects.all()):
        n = counts.get(c.pk, {})
        cards.append({'company': c, 'colour': SERIES[i % len(SERIES)], 'active': n.get('active', 0),
                      'left': n.get('left', 0), 'on': c == company})
    shown = [card for card in cards if not company or card['on']]
    month_start = office_today().replace(day=1)
    in_view = people.filter(company=company) if company else people
    stats = {
        'active': sum(c['active'] for c in shown), 'left': sum(c['left'] for c in shown),
        'left_this_month': in_view.filter(status=Employee.LEFT, left_on__gte=month_start).count(),
    }

    rows = in_view
    if f.get('status') == Employee.ACTIVE:
        rows = rows.filter(status=Employee.ACTIVE)
    elif f.get('status') == Employee.LEFT or dated:
        rows = rows.filter(left)
    page = Paginator(rows, PER_PAGE).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    return render(request, 'career_connect/hr/employees.html', {
        'filters': filters, 'page': page, 'cards': cards, 'stats': stats, 'company': company, 'dated': dated,
        'query': query.urlencode(), 'filtered': any(v for k, v in request.GET.items() if k != 'page'),
        'month_start': month_start, 'count': page.paginator.count, 'columns': [label for _, label in COLUMNS],
    })


def _back(request):
    url = request.POST.get('next') or request.GET.get('next') or ''
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return redirect(url)
    return redirect('hr_employees')


def _edit(request, employee=None):
    initial = {}
    if employee is None and request.GET.get('company'):
        initial['company'] = Company.objects.filter(slug=request.GET['company']).first()
    form = EmployeeForm(request.POST or None, instance=employee, initial=initial)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved.full_name} ({saved.company.name}) {"updated" if employee else "added"}.')
        if 'another' in request.POST:
            return redirect(f'{request.path}?company={saved.company.slug}')
        return _back(request)
    return render(request, 'career_connect/hr/employee_form.html', {
        'form': form, 'employee': employee, 'next': request.GET.get('next') or request.POST.get('next', ''),
        'departments': Employee.objects.exclude(department='').order_by('department')
                                       .values_list('department', flat=True).distinct(),
        'positions': Employee.objects.exclude(position='').order_by('position')
                                     .values_list('position', flat=True).distinct(),
    })


@hr_page
def employee_add(request):
    return _edit(request)


@hr_page
def employee_edit(request, employee_id):
    return _edit(request, get_object_or_404(Employee.objects.select_related('company', 'turnover'), pk=employee_id))


@hr_page
@require_POST
def employee_delete(request, employee_id):
    e = get_object_or_404(Employee, pk=employee_id)
    e.delete()
    messages.success(request, f'Removed {e.full_name} from the Employees list.')
    return _back(request)


def _cell(value):
    """A CSV cell that a spreadsheet won't run as a formula."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def _csv_response(name):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{name}"'
    response.write('﻿')   # so Excel reads it as UTF-8
    return response


@hr_page
def employees_export(request):
    """The employees on screen (with the filters applied, every page) as a CSV file."""
    filters, f, people, left = _filtered(request)
    if f.get('company'):
        people = people.filter(company=f['company'])
    if f.get('status') == Employee.ACTIVE:
        people = people.filter(status=Employee.ACTIVE)
    elif f.get('status') == Employee.LEFT or f.get('left_from') or f.get('left_to'):
        people = people.filter(left)
    response = _csv_response(f'employees-{office_today():%Y-%m-%d}.csv')
    out = csv.writer(response)
    out.writerow([label for _, label in COLUMNS])
    for e in people:
        out.writerow([_cell(v) for v in (
            e.employee_id, e.first_name, e.last_name, e.company.name, e.department, e.position, e.email, e.phone,
            e.start_date.isoformat() if e.start_date else '', e.get_status_display(),
            e.left_on.isoformat() if e.left_on else '', e.leaving_reason, e.notes)])
    return response


@hr_page
def employees_template(request):
    """An empty CSV with the right columns and one example row."""
    response = _csv_response('employees-template.csv')
    out = csv.writer(response)
    out.writerow([label for _, label in COLUMNS])
    company = Company.objects.first()
    out.writerow(['E001', 'Jane', 'Doe', company.name if company else 'Farmer Joe', 'Retail', 'Cashier',
                  'jane@example.com', '7712345', '2024-02-01', 'Active', '', '', ''])
    return response


def _read_csv(upload):
    raw = upload.read()
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError('The file is empty.')
    labels = {label.lower(): key for key, label in COLUMNS} | {key: key for key, _ in COLUMNS}
    header = [labels.get(h.strip().lower().lstrip('﻿')) for h in rows[0]]
    missing = {'first_name', 'company'} - set(header)
    if missing:
        names = dict(COLUMNS)
        raise ValueError('The file needs these columns: ' + ', '.join(names[m] for m in sorted(missing)) +
                         '. Download the template to see them all.')
    return [{k: (v or '').strip() for k, v in zip(header, row) if k} for row in rows[1:] if any(c.strip() for c in row)]


def _import_row(row, companies):
    """Adds or updates one employee from a CSV row: matched by company and employee ID, or by name when there's no
    ID. Returns (employee, created)."""
    company = companies.get(row.get('company', '').lower())
    if company is None:
        raise ValidationError(f'Company "{row.get("company", "")}" isn’t one of the companies in the SMS.')
    if not row.get('first_name'):
        raise ValidationError('First name is missing.')
    existing = Employee.objects.filter(company=company)
    if row.get('employee_id'):
        e = existing.filter(employee_id=row['employee_id']).first()
    else:
        e = existing.filter(employee_id='', first_name__iexact=row['first_name'],
                            last_name__iexact=row.get('last_name', '')).first()
    created = e is None
    e = e or Employee(company=company)
    for key in ('employee_id', 'first_name', 'last_name', 'department', 'position', 'email', 'phone',
                'leaving_reason', 'notes'):
        if key in row:
            setattr(e, key, row[key])
    for key in ('start_date', 'left_on'):
        if key in row:
            if row[key] and parse_day(row[key]) is None:
                raise ValidationError(f'"{row[key]}" isn’t a date (use 2026-11-03 or 3/11/2026).')
            setattr(e, key, parse_day(row[key]) if row[key] else None)
    status = row.get('status', '').lower()
    if status in ('left', 'leaver', 'resigned', 'terminated', 'inactive'):
        e.status = Employee.LEFT
    elif status in ('active', 'current', ''):
        e.status = Employee.LEFT if (not status and e.left_on) else Employee.ACTIVE
    else:
        raise ValidationError(f'Status "{row["status"]}" should be Active or Left.')
    if e.status == Employee.LEFT and e.left_on and e.left_on > office_today():
        raise ValidationError('The date they left is after today.')
    e.full_clean(exclude=['turnover'])
    e.save()
    return e, created


@hr_page
def employees_import(request):
    """Adds and updates employees from a CSV file. Nothing is saved unless every row is right."""
    errors = []
    if request.method == 'POST':
        upload = request.FILES.get('file')
        if not upload:
            errors.append('Choose a CSV file to import.')
        elif upload.size > MAX_IMPORT_MB * 1024 * 1024:
            errors.append(f'The file is too big (the limit is {MAX_IMPORT_MB} MB).')
        elif not upload.name.lower().endswith('.csv'):
            errors.append('The file must be a CSV (.csv). In Excel, use File › Save As › CSV UTF-8.')
        else:
            try:
                rows = _read_csv(upload)
            except (ValueError, csv.Error) as e:
                errors.append(str(e))
                rows = []
            if not rows and not errors:
                errors.append('The file has no employees in it.')
            companies = {}
            for c in Company.objects.all():
                companies[c.name.lower()] = companies[c.slug.lower()] = c
            added = updated = 0
            try:
                with transaction.atomic():
                    for n, row in enumerate(rows, start=2):
                        try:
                            _, created = _import_row(row, companies)
                        except ValidationError as e:
                            text = '; '.join(f'{k.replace("_", " ")}: {" ".join(v)}' if k != '__all__' else ' '.join(v)
                                             for k, v in e.message_dict.items()) if hasattr(e, 'error_dict') \
                                else ' '.join(e.messages)
                            errors.append(f'Row {n}: {text}')
                            continue
                        added, updated = added + created, updated + (not created)
                    if errors:
                        raise ValidationError('rolled back')
            except ValidationError:
                pass
            if not errors:
                messages.success(request, f'Imported the file: {added} employee{"s" if added != 1 else ""} added, '
                                          f'{updated} updated.')
                return redirect('hr_employees')
    return render(request, 'career_connect/hr/employees_import.html', {
        'errors': errors[:30], 'more_errors': max(len(errors) - 30, 0), 'columns': COLUMNS,
        'companies': Company.objects.all(), 'max_mb': MAX_IMPORT_MB,
    })
