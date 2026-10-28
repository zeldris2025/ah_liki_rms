"""Career Connect pages.

Public pages (no sign-in): they only ever read published Career Connect rows and never touch request.user,
the session, or any other part of the SMS. The one write is the expression-of-interest form, which only creates
ExpressionOfInterest rows for roles that have the form switched on.

Management (signed in, with the career_connect.manage_career_connect permission): the printable QR code.
Content itself is edited in the Django admin.
"""
import functools
import mimetypes

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from . import qr
from .access import MANAGE_PERMISSION
from .forms import InterestForm
from .models import Company, CompanyImage, Department, ExpressionOfInterest, PortalSettings, Role


def public_page(view):
    """Shows the 'not available' page while the portal is switched off, and hands the view the settings row."""
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        portal = PortalSettings.load()
        if not portal.is_published:
            return render(request, 'career_connect/unavailable.html', {'portal': portal}, status=503)
        request.portal = portal
        return view(request, *args, **kwargs)
    return wrapped


def _published_companies():
    """Published companies, each with the number of published roles in its published departments."""
    return Company.objects.filter(is_published=True).annotate(position_count=Count(
        'departments__roles', filter=Q(departments__is_published=True, departments__roles__is_published=True)))


def _published_departments(company):
    published_roles = Role.objects.filter(is_published=True)
    return (Department.objects.filter(is_published=True, company=company).select_related('company')
            .annotate(role_count=Count('roles', filter=Q(roles__is_published=True)))
            .prefetch_related(Prefetch('roles', queryset=published_roles, to_attr='published_roles')))


def _context(request, **extra):
    return {'portal': request.portal, **extra}


@require_GET
@public_page
def home(request):
    return render(request, 'career_connect/home.html', _context(
        request, companies=_published_companies(),
        images=CompanyImage.objects.filter(is_published=True)[:3], nav='home'))


@require_GET
@public_page
def about(request):
    return render(request, 'career_connect/about.html', _context(
        request, images=CompanyImage.objects.filter(is_published=True), nav='about'))


@require_GET
@public_page
def careers(request):
    return render(request, 'career_connect/careers.html', _context(
        request, companies=_published_companies(), nav='careers'))


@require_GET
@public_page
def company(request, company_slug):
    c = get_object_or_404(Company, slug=company_slug, is_published=True)
    return render(request, 'career_connect/company.html', _context(
        request, company=c, departments=_published_departments(c), nav='careers'))


def _published_department(company_slug, dept_slug):
    return get_object_or_404(Department.objects.select_related('company'), slug=dept_slug, is_published=True,
                             company__slug=company_slug, company__is_published=True)


@require_GET
@public_page
def department(request, company_slug, dept_slug):
    dept = _published_department(company_slug, dept_slug)
    return render(request, 'career_connect/department.html', _context(
        request, department=dept, roles=dept.roles.filter(is_published=True), nav='careers'))


def _published_role(company_slug, dept_slug, role_slug):
    """Only a published role, in a published department of a published company, reached through its own address."""
    return get_object_or_404(Role.objects.select_related('department__company'), slug=role_slug, is_published=True,
                             department__slug=dept_slug, department__is_published=True,
                             department__company__slug=company_slug, department__company__is_published=True)


@require_GET
@public_page
def role(request, company_slug, dept_slug, role_slug):
    r = _published_role(company_slug, dept_slug, role_slug)
    form = InterestForm() if r.accepts_interest else None
    return render(request, 'career_connect/role.html', _context(
        request, role=r, department=r.department, form=form, sent=request.GET.get('sent') == '1', nav='careers'))


def _client_ip(request):
    # Behind Azure / a proxy, the last X-Forwarded-For entry is the one the proxy itself added
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = forwarded.split(',')[-1].strip() if forwarded else request.META.get('REMOTE_ADDR', '')
    if ip.count(':') == 1:   # Azure adds the port: 1.2.3.4:5678
        ip = ip.split(':')[0]
    return ip[:64]


def _rate_limited(request):
    """At most CAREER_CONNECT_INTEREST_LIMIT submissions an hour from one address (a whole school shares one)."""
    key = 'career_connect:interest:' + _client_ip(request)
    count = cache.get(key, 0)
    if count >= settings.CAREER_CONNECT_INTEREST_LIMIT:
        return True
    cache.set(key, count + 1, 3600)
    return False


@require_POST
@public_page
def interest(request, company_slug, dept_slug, role_slug):
    r = _published_role(company_slug, dept_slug, role_slug)
    if not r.accepts_interest:
        raise Http404('This role does not take expressions of interest.')
    form = InterestForm(request.POST)
    if form.is_valid():
        if form.is_bot():
            return redirect(r.get_absolute_url() + '?sent=1')
        if _rate_limited(request):
            form.add_error(None, 'Too many submissions from your network. Please try again in an hour.')
        else:
            eoi = form.save(commit=False)
            eoi.role, eoi.role_title = r, r.title
            eoi.save()
            return redirect(r.get_absolute_url() + '?sent=1#apply')
    return render(request, 'career_connect/role.html', _context(
        request, role=r, department=r.department, form=form, sent=False, nav='careers'), status=400)


def _serve_photo(fieldfile):
    """A stored photo as an image response (never SVG, which could carry script)."""
    content_type = mimetypes.guess_type(fieldfile.name)[0] or ''
    if not content_type.startswith('image/') or content_type == 'image/svg+xml':
        raise Http404
    try:
        f = fieldfile.storage.open(fieldfile.name, 'rb')
    except (FileNotFoundError, ValueError):
        raise Http404('Image file missing.')
    response = FileResponse(f, content_type=content_type)
    response['Cache-Control'] = 'public, max-age=3600'
    return response


@require_GET
@public_page
def image(request, image_id):
    """Published Career Connect photos only. Other uploads stay behind the SMS sign-in (/media/)."""
    return _serve_photo(get_object_or_404(CompanyImage, pk=image_id, is_published=True).image)


@require_GET
@public_page
def company_image(request, company_slug):
    """A published company's background photo or logo."""
    c = get_object_or_404(Company, slug=company_slug, is_published=True)
    if not c.background:
        raise Http404
    return _serve_photo(c.background)


@require_GET
@public_page
def department_image(request, company_slug, dept_slug):
    """A published department's background photo."""
    dept = _published_department(company_slug, dept_slug)
    if not dept.background:
        raise Http404
    return _serve_photo(dept.background)


@login_required(login_url='login')
@permission_required(MANAGE_PERMISSION, raise_exception=True)
def manage_qr(request):
    """Preview and download the printable QR code."""
    url = qr.portal_url()
    fmt = request.GET.get('download')
    if fmt in ('png', 'svg'):
        body, content_type = (qr.png_bytes(url), 'image/png') if fmt == 'png' else (qr.svg_bytes(url), 'image/svg+xml')
        response = HttpResponse(body, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="ah-liki-career-connect-qr.{fmt}"'
        return response
    return render(request, 'career_connect/manage_qr.html', {
        'portal_url': url, 'problems': qr.url_problems(url), 'qr_data_uri': qr.png_data_uri(url),
        'portal': PortalSettings.load(),
        'interest_count': ExpressionOfInterest.objects.filter(reviewed=False).count(),
    })
