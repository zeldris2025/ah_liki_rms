"""Office access levels: Sales, Marketing and Manager.

A user's level comes from their group (Sales / Marketing / Manager). Superusers are Managers.
Sales and Marketing each have areas they can't open, and neither can download or export anything.
Staff with no level only get the areas both Sales and Marketing share.
"""
from django.shortcuts import render
from django.urls import Resolver404, resolve

SALES, MARKETING, MANAGER = 'Sales', 'Marketing', 'Manager'
ROLES = (SALES, MARKETING, MANAGER)

# URL names in each restricted area. Anything not listed (dashboard, clients, territories, atlas) is open to everyone.
AREAS = {
    'corporate_sales': {'corporate_sales', 'corporate_targets', 'corporate_manager',
                        'business_list', 'add_business', 'edit_business', 'delete_business'},
    'product_sales':   {'product_sales', 'product_sales_pin', 'quick_link_targets',
                        'product_group_add', 'product_group_edit', 'product_sales_export'},
    'promotions':      {'promotion_list', 'add_promotion', 'edit_promotion'},
    'sponsorships':    {'sponsorship_list', 'add_sponsorship', 'edit_sponsorship', 'delete_sponsorship'},
    'fe_ordering':     {'sales_export', 'product_list', 'product_add', 'product_edit', 'product_toggle',
                        'product_delete', 'product_import', 'product_template', 'product_export'},  # plus every fe_* URL
    'monthly_sales':   {'monthly_sales'},
    'surveys':         {'survey_list', 'add_survey', 'survey_detail', 'edit_survey', 'delete_survey', 'survey_analysis',
                        'add_survey_response', 'import_survey_responses', 'import_surveys', 'edit_survey_response', 'delete_survey_response'},
    'reports':         {'reports', 'download_report'},
    # Survey CSV imports sit under 'surveys' only, so Marketing can import surveys without Bulk Import
    'bulk_import':     {'import_shops', 'import_monthly_sales', 'import_product_sales', 'import_businesses',
                        'import_sponsorships', 'product_import', 'import_customer_product_sales',
                        'download_shop_template', 'download_business_template', 'download_sponsorship_template',
                        'download_survey_template', 'download_sales_template', 'download_product_sales_template',
                        'download_customer_product_sales_template', 'product_template'},
}

BLOCKED = {
    SALES:     {'product_sales', 'promotions', 'sponsorships', 'fe_ordering',
                'monthly_sales', 'surveys', 'reports', 'bulk_import'},   # Insights = monthly sales, surveys, reports
    MARKETING: {'corporate_sales', 'product_sales', 'monthly_sales', 'reports', 'bulk_import'},
    MANAGER:   set(),
}

# Downloads and exports: Managers only
EXPORT_URLS = {'download_report', 'product_sales_export', 'product_export', 'sales_export', 'product_template',
               'download_shop_template', 'download_business_template', 'download_sponsorship_template',
               'download_survey_template', 'download_sales_template', 'download_product_sales_template',
               'download_customer_product_sales_template'}


def roles_of(user):
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {MANAGER}
    return set(user.groups.filter(name__in=ROLES).values_list('name', flat=True))


def blocked_areas(user):
    """Areas this user can't open. Several levels combine: an area is open if any of them allows it."""
    roles = roles_of(user)
    if not roles:
        return set().union(*BLOCKED.values())
    return set.intersection(*(BLOCKED[r] for r in roles))


def areas_of(url_name):
    """Every area a URL belongs to (e.g. the product CSV import is both FE Ordering and Bulk Import)."""
    areas = {area for area, names in AREAS.items() if url_name in names}
    if url_name.startswith('fe_'):
        areas.add('fe_ordering')
    return areas


def can_see_sales(request):
    """Client sales figures belong to Corporate Sales and Monthly Sales; Marketing has neither."""
    return not {'corporate_sales', 'monthly_sales'} <= getattr(request, 'blocked_areas', set())


def role_label(user):
    roles = roles_of(user)
    for r in (MANAGER, MARKETING, SALES):
        if r in roles:
            return r
    return 'No access level'


class RoleAccessMiddleware:
    """Keeps Sales and Marketing out of their blocked areas and stops every download for them."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        # FE users are handled by FEAccessMiddleware; anonymous users by @login_required
        if not user.is_authenticated or getattr(request, 'is_fe', False):
            request.blocked_areas, request.can_export = set(), True
            return self.get_response(request)

        request.can_export = MANAGER in roles_of(user)
        request.blocked_areas = blocked_areas(user)
        if not request.can_export:
            try:
                match = resolve(request.path_info)
            except Resolver404:
                match = None
            if match:
                name = match.url_name or ''
                if match.app_name == 'admin':
                    return deny(request, 'the admin site')
                if areas_of(name) & request.blocked_areas:
                    return deny(request, 'this page')
                if name in EXPORT_URLS or 'export' in request.GET:
                    return deny(request, 'downloads and exports')

        response = self.get_response(request)
        # Safety net: whatever the page, a non-Manager never receives a file download
        if not request.can_export and 'attachment' in response.get('Content-Disposition', ''):
            return deny(request, 'downloads and exports')
        return response



def deny(request, what):
    """The 'No access' page, e.g. deny(request, 'this page')."""
    return render(request, 'shops/no_access.html', {'what': what, 'role': role_label(request.user)}, status=403)


def access_context(request):
    blocked = getattr(request, 'blocked_areas', set())
    return {
        'access': {area: area not in blocked for area in AREAS},
        'can_export': getattr(request, 'can_export', True),
        'see_sales': can_see_sales(request),
        'user_role': role_label(request.user) if getattr(request, 'user', None) else '',
    }
