"""HR vacancies: HR post, update, open/close and remove the positions (roles) of every company in the group.

Signed in with the career_connect.manage_vacancies permission (the 'HR' group; superusers too). Companies,
departments and the portal settings stay in the Django admin.
"""
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .access import VACANCY_PERMISSION
from .forms import TurnoverForm, VacancyFilterForm, VacancyForm, leaver_label
from .models import (Company, Employee, ExpressionOfInterest, Role, StaffTurnover, live_roles_q, office_today, recruiting_q,
                     turnover_rate, week_label)


def hr_page(view):
    return login_required(permission_required(VACANCY_PERMISSION, raise_exception=True)(view), login_url='login')


def _back(request):
    """Back to the list the action was started from (its filters kept), never to another site."""
    url = request.POST.get('next', '')
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return redirect(url)
    return redirect('hr_vacancies')


PERIODS = (6, 12, 24)   # months the dashboard can look back over


def _office_tz():
    return ZoneInfo(settings.CAREER_CONNECT_TIME_ZONE)


def _month(dt, tz):
    local = timezone.localtime(dt, tz)
    return local.year, local.month


def _pct(part, whole):
    return round(100 * part / whole, 1) if whole else 0


# Categorical series colours, in this fixed order (a company keeps its colour whatever is shown)
SERIES = ('#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948')


def _month_keys(months):
    """(year, month) for the last `months` months in office time, oldest first, ending with this one."""
    today = office_today()
    y, m = today.year, today.month
    keys = []
    for _ in range(months):
        keys.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return keys[::-1]


def _save_headcount(request, month):
    """Change one company's kept number of employees (from the Number of employees card)."""
    company = get_object_or_404(Company, pk=request.POST.get('company') or 0)
    try:
        count = int(request.POST.get('headcount', ''))
    except ValueError:
        count = 0
    if count < 1:
        messages.error(request, f'Enter how many employees {company.name} has (1 or more).')
    else:
        company.employee_count = count
        company.save(update_fields=['employee_count'])
        messages.success(request, f'{company.name} now has {count} employees. Weeks already saved keep their own number.')
    return redirect(f'{request.path}?month={month:%Y-%m}')


def _names(people):
    names = [p.full_name for p in people]
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


def _back_to_work(employees):
    """Employees taken off a week's list of leavers (or whose week is removed) are active again."""
    back = list(employees)
    for e in back:
        e.status = Employee.ACTIVE   # save() clears the leaving date, reason and week
        e.save()
    return back


def _suggestions(editing=None):
    """The names the turnover form suggests, by company: active employees, plus those named in the week being edited."""
    people = Employee.objects.filter(Q(status=Employee.ACTIVE) | Q(turnover=editing) if editing else
                                     Q(status=Employee.ACTIVE))
    out = {}
    for e in people.only('pk', 'company_id', 'first_name', 'last_name', 'position', 'employee_id'):
        out.setdefault(e.company_id, []).append({'id': e.pk, 'label': leaver_label(e)})
    return out


def _monday(day):
    return day - timedelta(days=day.weekday())


def _weeks_of(month):
    """The Mondays in a month: its weeks (a week belongs to the month its Monday is in)."""
    day = month.replace(day=1)
    day += timedelta(days=(7 - day.weekday()) % 7)
    weeks = []
    while day.month == month.month:
        weeks.append(day)
        day += timedelta(days=7)
    return weeks


def _combine(records):
    """A month (or any set of weeks): everyone who left ÷ the average number of employees × 100."""
    if not records:
        return None
    left = sum(r.leavers for r in records)
    staff = Decimal(sum(r.employees for r in records)) / len(records)
    return {'leavers': left, 'employees': staff, 'staff': round(staff), 'weeks': len(records),
            'rate': float(turnover_rate(left, staff))}


def _turnover_series(keys, only=None):
    """Each company's monthly turnover % from its weekly figures (None for a month with none), and its latest month.
    With `only`, just that company's line (in the same colour it has among all of them)."""
    since = date(*keys[0], 1)
    weekly = {}
    for t in StaffTurnover.objects.filter(week__gte=since):
        weekly.setdefault((t.company_id, t.week.year, t.week.month), []).append(t)
    series = []
    for i, company in enumerate(Company.objects.all()):
        if only and company != only:
            continue
        last = StaffTurnover.objects.filter(company=company).order_by('-week').first()
        latest = _combine(list(StaffTurnover.objects.filter(
            company=company, week__year=last.week.year, week__month=last.week.month))) if last else None
        months = [_combine(weekly.get((company.pk, y, m), [])) for y, m in keys]
        series.append({
            'name': company.name, 'colour': SERIES[i % len(SERIES)],
            'data': [m['rate'] if m else None for m in months],
            'latest': latest['rate'] if latest else None, 'latest_month': last.week.replace(day=1) if last else None,
            'leavers': latest['leavers'] if latest else 0, 'employees': latest['employees'] if latest else 0,
        })
    return series


@hr_page
def dashboard(request):
    """Recruitment at a glance: the roles we're recruiting for, applicants, interviews, hires, the hire rate and
    each company's staff turnover, month by month over the chosen period. ?company=<slug> narrows everything to one
    company (all of them by default)."""
    E = ExpressionOfInterest
    tz, now = _office_tz(), timezone.now()
    try:
        months = int(request.GET.get('months', 12))
    except ValueError:
        months = 12
    months = months if months in PERIODS else 12

    keys = _month_keys(months)
    since = datetime(*keys[0], 1, tzinfo=tz)

    companies = list(Company.objects.all())
    company = next((c for c in companies if c.slug == request.GET.get('company')), None)
    applications = E.objects.filter(role__company=company) if company else E.objects.all()
    roles = Role.objects.filter(company=company) if company else Role.objects.all()

    apps = list(applications.values('created_at', 'stage', 'interview_at', 'stage_changed_at'))
    in_period = [a for a in apps if a['created_at'] >= since]
    hired = [a for a in apps if a['stage'] == E.HIRED and (a['stage_changed_at'] or a['created_at']) >= since]
    interviews = [a for a in apps if a['interview_at'] and since <= a['interview_at'] <= now]

    per_app = Counter(_month(a['created_at'], tz) for a in in_period)
    per_int = Counter(_month(a['interview_at'], tz) for a in interviews)
    per_hire = Counter(_month(a['stage_changed_at'] or a['created_at'], tz) for a in hired)
    cohort_hired = Counter(_month(a['created_at'], tz) for a in in_period if a['stage'] == E.HIRED)
    chart = {
        'labels': [datetime(yy, mm, 1).strftime('%b %Y') for yy, mm in keys],
        'applications': [per_app[k] for k in keys],
        'interviews': [per_int[k] for k in keys],
        'hires': [per_hire[k] for k in keys],
        'hire_rate': [_pct(cohort_hired[k], per_app[k]) if per_app[k] else None for k in keys],
        'companies': _turnover_series(keys, company),
    }

    hire_days = [((a['stage_changed_at'] or a['created_at']) - a['created_at']).days for a in hired]
    stats = {
        'applicants': len(in_period),
        'this_month': per_app[_month(now, tz)],
        'interviews': len(interviews),
        'upcoming': sum(1 for a in apps if a['interview_at'] and a['interview_at'] > now),
        'hired': len(hired),
        'hire_rate': _pct(sum(cohort_hired.values()), len(in_period)),
        'interview_rate': _pct(sum(1 for a in in_period if a['interview_at'] or a['stage'] in E.INTERVIEWED),
                               len(in_period)),
        'to_review': sum(1 for a in apps if a['stage'] == E.NEW),
        'days_to_hire': round(sum(hire_days) / len(hire_days)) if hire_days else None,
    }

    stage_counts = Counter(a['stage'] for a in in_period)
    top = max(stage_counts.values(), default=0)
    pipeline = [{'key': key, 'label': label, 'count': stage_counts[key], 'pct': _pct(stage_counts[key], top)}
                for key, label in E.STAGES]

    vacant = (roles.filter(live_roles_q() & recruiting_q(Role.OPEN)).select_related('company', 'department')
              .annotate(applicants=Count('interests'),
                        new=Count('interests', filter=Q(interests__stage=E.NEW)),
                        interviewing=Count('interests', filter=Q(interests__stage__in=E.INTERVIEWED)),
                        hires=Count('interests', filter=Q(interests__stage=E.HIRED)))
              .order_by('expires_on', 'company__order', 'title'))

    # Applicants by company, or by department within one company
    group = 'role__department__name' if company else 'role__company__name'
    by_group = list(applications.filter(created_at__gte=since, role__isnull=False)
                    .values(group).annotate(n=Count('id')).order_by('-n')[:6])
    top_group = by_group[0]['n'] if by_group else 0
    vacant_by_company = Counter(Role.objects.filter(live_roles_q() & recruiting_q(Role.OPEN))
                                .values_list('company_id', flat=True))

    # Each company's latest month, combined with the same formula (not an average of the percentages)
    latest = [c for c in chart['companies'] if c['latest'] is not None]
    left, staff = sum(c['leavers'] for c in latest), sum(c['employees'] for c in latest)
    stats['staff_turnover'] = float(turnover_rate(left, staff)) if latest else None
    stats['turnover_companies'], stats['turnover_left'], stats['turnover_staff'] = len(latest), left, round(staff)

    return render(request, 'career_connect/hr/dashboard.html', {
        'months': months, 'periods': PERIODS, 'stats': stats, 'chart': chart, 'pipeline': pipeline,
        'vacant': vacant, 'live_count': roles.filter(live_roles_q()).count(),
        'company': company, 'tabs': [{'company': c, 'vacant': vacant_by_company[c.pk], 'colour': SERIES[i % len(SERIES)]}
                                    for i, c in enumerate(companies)],
        'all_vacant': sum(vacant_by_company.values()),
        'by_group': [{'name': g[group] or 'No department', 'n': g['n'], 'pct': _pct(g['n'], top_group)}
                     for g in by_group],
        'upcoming': applications.filter(interview_at__gt=now).select_related('role__company').order_by('interview_at')[:6],
        'recent': applications.select_related('role__company')[:6],
    })


@hr_page
def turnover(request):
    """HR enter each company's staff turnover week by week, and correct or remove a week. The table shows one month's
    weeks (this month unless ?month=YYYY-MM picks another) and each company's total for the month; clicking a cell
    fills the form with that company and week."""
    today = office_today()
    this_month = today.replace(day=1)
    try:
        month = datetime.strptime(request.GET.get('month', ''), '%Y-%m').date()
    except ValueError:
        month = this_month
    month = min(month, this_month)
    weeks = _weeks_of(month)
    open_weeks = [w for w in weeks if w <= today]   # this week and earlier can be filled in

    if request.method == 'POST' and 'headcount' in request.POST:
        return _save_headcount(request, month)
    if request.method == 'POST':
        form = TurnoverForm(request.POST, weeks=open_weeks)
        if form.is_valid():
            company, week = form.cleaned_data['company'], form.cleaned_data['week']
            if request.POST.get('remove'):
                record = StaffTurnover.objects.filter(company=company, week=week).first()
                said = f'Removed {company.name}’s turnover for the week of {week_label(week)}.'
                if record:
                    back = _back_to_work(record.leavers_named.all())
                    record.delete()
                    if back:
                        said += f' {_names(back)} {"is" if len(back) == 1 else "are"} active again.'
                messages.success(request, said)
            else:
                with transaction.atomic():
                    saved, _ = StaffTurnover.objects.update_or_create(company=company, week=week, defaults={
                        'leavers': form.cleaned_data['leavers'], 'employees': form.cleaned_data['employees'],
                        'note': form.cleaned_data['note'],
                        'updated_by': request.user.get_full_name() or request.user.get_username()})
                    # The employees named are marked as left, in this week; anyone taken off the list is active again
                    named = {e.pk for e, _, _ in form.named}
                    back = _back_to_work(saved.leavers_named.exclude(pk__in=named))
                    for employee, left_on, reason in form.named:
                        employee.status, employee.left_on, employee.turnover = Employee.LEFT, left_on, saved
                        employee.leaving_reason = reason or employee.leaving_reason
                        employee.save()
                said = (f'{company.name}, week of {week_label(week)}: {saved.leavers} of {saved.employees} '
                        f'employees left, {saved.rate}% turnover.')
                if form.named:
                    said += f' Marked as left: {_names([e for e, _, _ in form.named])}.'
                if back:
                    said += f' {_names(back)} {"is" if len(back) == 1 else "are"} active again.'
                latest = not StaffTurnover.objects.filter(company=company, week__gt=week).exists()
                # A new number of employees is kept from now on, unless HR are correcting an older week
                if latest and saved.employees != company.employee_count:
                    company.employee_count = saved.employees
                    company.save(update_fields=['employee_count'])
                    said += f' {company.name} now has {saved.employees} employees.'
                messages.success(request, said)
            return redirect(f'{request.path}?month={week:%Y-%m}&company={company.pk}&week={week}')
    else:
        this_week = _monday(today)
        initial = {'week': this_week if this_week in open_weeks else (open_weeks[-1] if open_weeks else None)}
        company = Company.objects.filter(pk=request.GET.get('company') or 0).first()
        try:
            picked = date.fromisoformat(request.GET.get('week', ''))
        except ValueError:
            picked = None
        if picked in open_weeks:
            initial['week'] = picked
        existing = None
        if company:
            initial['company'] = company
            existing = StaffTurnover.objects.filter(company=company, week=initial['week']).first()
            if existing:
                initial.update(leavers=existing.leavers, employees=existing.employees, note=existing.note)
            else:   # the company's kept number of employees
                initial['employees'] = company.employee_count
        named = list(existing.leavers_named.all()) if company and existing else []
        if initial['week']:
            initial['week'] = initial['week'].isoformat()
        form = TurnoverForm(initial=initial, weeks=open_weeks, named=named)

    try:
        editing = StaffTurnover.objects.filter(company_id=int(form['company'].value() or 0),
                                               week=date.fromisoformat(str(form['week'].value() or ''))).first()
    except ValueError:
        editing = None
    records = {(t.company_id, t.week): t for t in StaffTurnover.objects.filter(week__in=weeks)}
    on_list = dict(Employee.objects.filter(status=Employee.ACTIVE).values('company')
                   .annotate(n=Count('pk')).values_list('company', 'n'))
    rows = []
    for i, c in enumerate(Company.objects.all()):
        cells = [{'week': w, 'record': records.get((c.pk, w)), 'future': w > today} for w in weeks]
        rows.append({'company': c, 'colour': SERIES[i % len(SERIES)], 'cells': cells, 'on_list': on_list.get(c.pk, 0),
                     'month': _combine([cell['record'] for cell in cells if cell['record']])})
    group = [_combine([records[k] for k in records if k[1] == w]) for w in weeks]
    prev_month = (month - timedelta(days=1)).replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)
    return render(request, 'career_connect/hr/turnover.html', {
        'form': form, 'rows': rows, 'this_month': this_month,
        'headcounts': {c.pk: c.employee_count for c in Company.objects.all()},
        'people': _suggestions(editing),
        'weeks': [{'monday': w, 'label': week_label(w), 'future': w > today, 'current': w == _monday(today)} for w in weeks],
        'group': group, 'group_month': _combine(list(records.values())), 'editing': editing,
        'month': month, 'is_this_month': month == this_month, 'prev_month': prev_month,
        'next_month': next_month if next_month <= this_month else None,
        'recent': StaffTurnover.objects.select_related('company').order_by('-updated_at')[:8],
    })


@hr_page
def vacancies(request):
    roles = Role.objects.select_related('company', 'department').annotate(
        interest_count=Count('interests', filter=Q(interests__reviewed=False)), application_count=Count('interests'))
    live = live_roles_q()
    expired = Q(expires_on__lte=office_today())
    stats = roles.aggregate(
        total=Count('id'),
        open=Count('id', filter=live & recruiting_q(Role.OPEN)),
        live=Count('id', filter=live),
        drafts=Count('id', filter=Q(is_published=False)),
        expired=Count('id', filter=Q(is_published=True) & expired))

    filters = VacancyFilterForm(request.GET or None)
    if filters.is_valid():
        q, company, status = (filters.cleaned_data[k] for k in ('q', 'company', 'status'))
        if q:
            roles = roles.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(department__name__icontains=q))
        if company:
            roles = roles.filter(company=company)
        if status == 'draft':
            roles = roles.filter(is_published=False)
        elif status == 'expired':
            roles = roles.filter(expired)
        elif status:
            roles = roles.filter(recruiting_q(status))

    groups = {}
    for role in roles:
        groups.setdefault(role.company, []).append(role)
    return render(request, 'career_connect/hr/vacancies.html', {
        'groups': list(groups.items()), 'stats': stats, 'filters': filters, 'filtered': bool(request.GET),
        'company_count': Company.objects.count(), 'Role': Role,
    })


def _edit(request, role=None):
    form = VacancyForm(request.POST or None, request.FILES or None, instance=role)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'“{saved.title}” {"updated" if role else "added"} for {saved.place}.')
        return redirect('hr_vacancies')
    return render(request, 'career_connect/hr/vacancy_form.html', {'form': form, 'role': role})


@hr_page
def vacancy_add(request):
    return _edit(request)


@hr_page
def vacancy_edit(request, role_id):
    return _edit(request, get_object_or_404(Role.objects.select_related('company', 'department'), pk=role_id))


STATUS_ACTIONS = {
    'open':    ({'vacancy_status': Role.OPEN}, 'is now marked as currently recruiting'),
    'closed':  ({'vacancy_status': Role.CLOSED}, 'is now marked as not currently recruiting'),
    'publish': ({'is_published': True}, 'is now showing on Career Connect'),
    'hide':    ({'is_published': False}, 'is now hidden from Career Connect'),
}


@require_POST
@hr_page
def vacancy_status(request, role_id):
    role = get_object_or_404(Role, pk=role_id)
    action = request.POST.get('action')
    change = STATUS_ACTIONS.get(action)
    if change and action in ('open', 'closed') and role.expires_on:
        messages.error(request, f'“{role.title}” has an expiry date, which sets its recruiting status. '
                                'Change or clear the date instead.')
    elif change:
        fields, said = change
        for name, value in fields.items():
            setattr(role, name, value)
        role.save(update_fields=list(fields))
        messages.success(request, f'“{role.title}” {said}.')
    return _back(request)


@require_POST
@hr_page
def vacancy_delete(request, role_id):
    role = get_object_or_404(Role, pk=role_id)
    role.delete()   # expressions of interest already sent are kept (their role is cleared)
    messages.success(request, f'“{role.title}” was removed.')
    return _back(request)


@hr_page
def applications(request, role_id):
    """Everyone who applied for one position, newest first, with their files."""
    role = get_object_or_404(Role.objects.select_related('company', 'department'), pk=role_id)
    applications = list(role.interests.all())
    tz = _office_tz()
    for a in applications:
        a.interview_local = timezone.localtime(a.interview_at, tz) if a.interview_at else None
    return render(request, 'career_connect/hr/applications.html', {
        'role': role, 'applications': applications, 'stages': ExpressionOfInterest.STAGES,
    })


@require_POST
@hr_page
def application_reviewed(request, app_id):
    app = get_object_or_404(ExpressionOfInterest, pk=app_id)
    reviewed = request.POST.get('reviewed') == '1'
    if reviewed != app.reviewed and app.stage in (ExpressionOfInterest.NEW, ExpressionOfInterest.REVIEWED):
        app.stage = ExpressionOfInterest.REVIEWED if reviewed else ExpressionOfInterest.NEW
        app.save(update_fields=['stage'])
    return _back(request)


@require_POST
@hr_page
def application_stage(request, app_id):
    """Move an applicant along: New, Reviewed, Interview (with its date and time), Offered, Hired or Unsuccessful."""
    E = ExpressionOfInterest
    app = get_object_or_404(E, pk=app_id)
    stage = request.POST.get('stage')
    if stage not in dict(E.STAGES):
        messages.error(request, 'Choose a stage.')
        return _back(request)
    raw = request.POST.get('interview_at', '').strip()
    when = parse_datetime(raw) if raw else None
    if raw and when is None:
        messages.error(request, 'That interview date is not valid.')
        return _back(request)
    if stage == E.INTERVIEW and not (when or app.interview_at):
        messages.error(request, f'Pick the interview date and time for {app.full_name}.')
        return _back(request)
    if when:
        app.interview_at = timezone.make_aware(when, _office_tz()) if timezone.is_naive(when) else when
    app.stage = stage
    app.save(update_fields=['stage', 'interview_at'])
    said = f'{app.full_name}: {app.get_stage_display()}'
    if stage == E.INTERVIEW:
        said += f', interview {timezone.localtime(app.interview_at, _office_tz()):%a %d %b, %I:%M %p}'
    messages.success(request, said + '.')
    return _back(request)


@hr_page
def application_file(request, app_id, kind):
    """An applicant's CV, cover letter or qualifications: only ever handed out here, to HR, as a download."""
    app = get_object_or_404(ExpressionOfInterest, pk=app_id)
    if kind not in dict(ExpressionOfInterest.ATTACHMENTS) or not getattr(app, kind):
        raise Http404
    f = getattr(app, kind)
    try:
        handle = f.open('rb')
    except (FileNotFoundError, ValueError):
        raise Http404('File missing.')
    ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else 'pdf'
    label = dict(ExpressionOfInterest.ATTACHMENTS)[kind]
    response = FileResponse(handle, as_attachment=True, filename=f'{app.full_name} - {label}.{ext}')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
