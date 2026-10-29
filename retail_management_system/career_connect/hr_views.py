"""HR vacancies: HR post, update, open/close and remove the positions (roles) of every company in the group.

Signed in with the career_connect.manage_vacancies permission (the 'HR' group; superusers too). Companies,
departments and the portal settings stay in the Django admin.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .access import VACANCY_PERMISSION
from .forms import VacancyFilterForm, VacancyForm
from .models import Company, Role


def hr_page(view):
    return login_required(permission_required(VACANCY_PERMISSION, raise_exception=True)(view), login_url='login')


def _back(request):
    """Back to the list the action was started from (its filters kept), never to another site."""
    url = request.POST.get('next', '')
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return redirect(url)
    return redirect('hr_vacancies')


@hr_page
def vacancies(request):
    roles = Role.objects.select_related('department__company').annotate(
        interest_count=Count('interests', filter=Q(interests__reviewed=False)))
    stats = roles.aggregate(
        total=Count('id'),
        open=Count('id', filter=Q(is_published=True, vacancy_status=Role.OPEN)),
        live=Count('id', filter=Q(is_published=True)),
        drafts=Count('id', filter=Q(is_published=False)))

    filters = VacancyFilterForm(request.GET or None)
    if filters.is_valid():
        q, company, status = (filters.cleaned_data[k] for k in ('q', 'company', 'status'))
        if q:
            roles = roles.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(department__name__icontains=q))
        if company:
            roles = roles.filter(department__company=company)
        if status == 'draft':
            roles = roles.filter(is_published=False)
        elif status:
            roles = roles.filter(vacancy_status=status)

    groups = {}
    for role in roles:
        groups.setdefault(role.department.company, []).append(role)
    return render(request, 'career_connect/hr/vacancies.html', {
        'groups': list(groups.items()), 'stats': stats, 'filters': filters, 'filtered': bool(request.GET),
        'company_count': Company.objects.count(), 'Role': Role,
    })


def _edit(request, role=None):
    form = VacancyForm(request.POST or None, instance=role)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'“{saved.title}” {"updated" if role else "added"} for '
                                  f'{saved.department.company} · {saved.department.name}.')
        return redirect('hr_vacancies')
    return render(request, 'career_connect/hr/vacancy_form.html', {'form': form, 'role': role})


@hr_page
def vacancy_add(request):
    return _edit(request)


@hr_page
def vacancy_edit(request, role_id):
    return _edit(request, get_object_or_404(Role.objects.select_related('department__company'), pk=role_id))


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
    change = STATUS_ACTIONS.get(request.POST.get('action'))
    if change:
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
