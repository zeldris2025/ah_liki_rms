import re
import shutil
import tempfile

from django.contrib.auth.models import Group, Permission, User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from . import qr
from .access import PUBLIC_URL_NAMES
from .models import Company, CompanyImage, Department, ExpressionOfInterest, PortalSettings, Role, video_embed_url

def _png():
    """A small real PNG (Pillow checks uploads are genuine images)."""
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', (4, 3), (30, 111, 224)).save(buf, 'PNG')
    return buf.getvalue()


PNG = _png()

SMS_ONLY_TEXT = ('Logout', 'Sales and Marketing', 'All Clients', 'Car Allocations')


def _user(name, *groups, **extra):
    u = User.objects.create_user(name, password='pw-123456', **extra)
    for g in groups:
        u.groups.add(Group.objects.get_or_create(name=g)[0])
    return u


class PublicPortalTests(TestCase):
    """Students: every public page opens without signing in and shows nothing from the SMS."""

    def setUp(self):
        cache.clear()
        self.finance = Department.objects.get(company__slug='ah-liki-wholesale', slug='finance')
        self.accountant = Role.objects.get(department=self.finance, slug='accountant')

    def test_seeded_departments_and_roles(self):
        self.assertEqual(
            list(Department.objects.filter(company__slug='ah-liki-wholesale').values_list('name', flat=True)),
            ['Finance Department', 'Marketing Department', 'HR Department', 'Sales Department',
             'Warehouse Operation', 'Trades Department'])
        self.assertEqual(Role.objects.count(), 11)
        # Nothing invented: no descriptions, vacancy status not stated, no apply button until an admin turns it on
        self.assertFalse(Role.objects.exclude(description='').exists())
        self.assertFalse(Role.objects.exclude(vacancy_status=Role.NOT_STATED).exists())
        self.assertFalse(Role.objects.exclude(apply_method=Role.APPLY_NONE).exists())

    def test_every_public_page_opens_signed_out(self):
        urls = [reverse('career_connect')]
        urls += [c.get_absolute_url() for c in Company.objects.all()]
        for d in Department.objects.all():
            urls.append(d.get_absolute_url())
            urls += [r.get_absolute_url() for r in d.roles.all()]
        self.assertEqual(len(urls), 1 + 5 + 5 * 6 + 11)
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, 'Career Connect')
            for text in SMS_ONLY_TEXT:
                self.assertNotContains(r, text, msg_prefix=url)

    def test_home_lists_companies_with_links(self):
        r = self.client.get(reverse('career_connect'))
        self.assertContains(r, 'Discover Opportunities. Build Your Future.')
        for c in Company.objects.all():
            self.assertContains(r, f'href="{c.get_absolute_url()}"')
        self.assertNotContains(r, 'not provided yet')

    def test_hiring_popup_lists_open_roles_only(self):
        self.assertNotContains(self.client.get(reverse('career_connect')), 'id="hiring"')   # none recruiting yet
        accountant = Role.objects.get(slug='accountant')
        accountant.vacancy_status = Role.OPEN
        accountant.save()
        r = self.client.get(reverse('career_connect'))
        self.assertContains(r, '<dialog class="hiring"')
        self.assertContains(r, '1 position open now')
        self.assertContains(r, f'href="{accountant.get_absolute_url()}"')
        self.assertEqual([x.pk for x in r.context['hiring']], [accountant.pk])
        accountant.department.is_published = False
        accountant.department.save()
        self.assertNotContains(self.client.get(reverse('career_connect')), 'id="hiring"')

    def test_old_about_and_careers_links_go_to_career_opportunities(self):
        for name in ('career_connect_about', 'career_connect_careers'):
            self.assertRedirects(self.client.get(reverse(name)), reverse('career_connect'))

    def test_every_link_on_public_pages_works(self):
        """No dead buttons: each internal link on each page answers 200 for a signed-out visitor."""
        seen, todo = set(), [reverse('career_connect')]
        while todo:
            url = todo.pop()
            if url in seen:
                continue
            seen.add(url)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            for href in re.findall(r'href="(/[^"#?]*)', r.content.decode()):
                if not href.startswith('/static/'):
                    self.assertTrue(href.startswith('/career-connect/'), f'{url} links outside the portal: {href}')
                    todo.append(href)
        self.assertGreaterEqual(len(seen), 20)

    def test_unpublished_content_is_hidden(self):
        self.accountant.is_published = False
        self.accountant.save()
        self.assertEqual(self.client.get(self.accountant.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(self.finance.get_absolute_url()), 'Accountant')
        self.finance.is_published = False
        self.finance.save()
        self.assertEqual(self.client.get(self.finance.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse('career_connect_role', args=['ah-liki-wholesale', 'finance', 'finance-officer'])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('career_connect_company', args=['ah-liki-wholesale'])),
                               'Finance Department')

    def test_careers_page_lists_the_ah_liki_investment_companies(self):
        r = self.client.get(reverse('career_connect'))
        self.assertContains(r, 'Companies of Ah Liki Investment')
        names = ['Ah Liki Wholesale', 'Farmer Joe', 'Taula', 'Burger Bills', 'Tanumapua Farm']
        self.assertEqual(list(Company.objects.values_list('name', flat=True)), names)
        html = r.content.decode()
        self.assertEqual([html.index(n) for n in names], sorted(html.index(n) for n in names))
        for c in Company.objects.all():
            self.assertContains(r, f'href="{c.get_absolute_url()}"')
        self.assertContains(r, '11 Available Positions')
        self.assertContains(r, '0 Available Positions', count=4)
        # Unpublished roles and departments are not counted
        self.accountant.is_published = False
        self.accountant.save()
        Department.objects.filter(company__slug='ah-liki-wholesale', slug='trades').update(is_published=False)
        self.assertContains(self.client.get(reverse('career_connect')), '7 Available Positions')

    def test_company_page_shows_its_departments(self):
        r = self.client.get(reverse('career_connect_company', args=['ah-liki-wholesale']))
        for d in Department.objects.filter(company__slug='ah-liki-wholesale'):
            self.assertContains(r, f'href="{d.get_absolute_url()}"')
        r = self.client.get(reverse('career_connect_company', args=['farmer-joe']))
        self.assertContains(r, 'href="/career-connect/careers/farmer-joe/finance/"')
        self.assertNotContains(r, f'href="{self.finance.get_absolute_url()}"')
        Company.objects.filter(slug='taula').update(is_published=False)
        self.assertEqual(self.client.get(reverse('career_connect_company', args=['taula'])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('career_connect')), 'Taula')

    def test_same_department_name_in_two_companies(self):
        farmer_joe = Company.objects.get(slug='farmer-joe')
        dept = Department.objects.get(company=farmer_joe, slug='finance')
        Role.objects.create(department=dept, title='Bookkeeper', slug='bookkeeper')
        self.assertEqual(dept.get_absolute_url(), '/career-connect/careers/farmer-joe/finance/')
        self.assertNotContains(self.client.get(self.finance.get_absolute_url()), 'Bookkeeper')
        self.assertContains(self.client.get(dept.get_absolute_url()), 'Bookkeeper')
        r = self.client.get(reverse('career_connect_role', args=['ah-liki-wholesale', 'finance', 'bookkeeper']))
        self.assertEqual(r.status_code, 404)

    def test_role_page_asks_to_email_hr_for_the_job_description(self):
        self.accountant.description = 'Secret internal description'
        self.accountant.save()
        r = self.client.get(self.accountant.get_absolute_url())
        self.assertContains(r, 'href="mailto:hr@ahliki.com?subject=Accountant')
        self.assertNotContains(r, 'Secret internal description')

    def test_role_only_under_its_own_department(self):
        r = self.client.get(reverse('career_connect_role', args=['ah-liki-wholesale', 'marketing', 'accountant']))
        self.assertEqual(r.status_code, 404)

    def test_portal_switched_off(self):
        p = PortalSettings.load()
        p.is_published = False
        p.save()
        for url in (reverse('career_connect'), self.accountant.get_absolute_url()):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 503)
            self.assertContains(r, 'not available', status_code=503)

    def test_content_is_escaped(self):
        p = PortalSettings.load()
        p.hero_text = '<script>alert(1)</script>'
        p.save()
        r = self.client.get(reverse('career_connect'))
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.assertContains(r, '&lt;script&gt;')

    def test_read_only_methods(self):
        for url in (reverse('career_connect'), self.accountant.get_absolute_url()):
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_video_embeds(self):
        self.assertEqual(video_embed_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
                         'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
        self.assertEqual(video_embed_url('https://youtu.be/dQw4w9WgXcQ'),
                         'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
        self.assertEqual(video_embed_url('https://vimeo.com/12345'), 'https://player.vimeo.com/video/12345')
        self.assertTrue(video_embed_url('https://www.facebook.com/ahliki/videos/1/').startswith(
            'https://www.facebook.com/plugins/video.php'))
        self.assertEqual(video_embed_url('https://example.com/video.mp4'), '')
        self.assertEqual(video_embed_url('javascript:alert(1)'), '')


class ExpressionOfInterestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.role = Role.objects.get(slug='accountant')
        self.url = reverse('career_connect_interest', args=['ah-liki-wholesale', 'finance', 'accountant'])
        self.data = {'full_name': 'Lagi Student', 'email': 'lagi@example.com', 'school': 'Apia High', 'consent': 'on'}

    def enable(self):
        self.role.apply_method = Role.APPLY_FORM
        self.role.save()

    def test_form_only_when_enabled(self):
        self.assertNotContains(self.client.get(self.role.get_absolute_url()), 'Send my interest')
        self.assertEqual(self.client.post(self.url, self.data).status_code, 404)
        self.assertFalse(ExpressionOfInterest.objects.exists())
        self.enable()
        self.assertContains(self.client.get(self.role.get_absolute_url()), 'Send my interest')

    def test_submit(self):
        self.enable()
        r = self.client.post(self.url, self.data)
        self.assertRedirects(r, self.role.get_absolute_url() + '?sent=1#apply', fetch_redirect_response=False)
        eoi = ExpressionOfInterest.objects.get()
        self.assertEqual((eoi.role, eoi.role_title, eoi.full_name), (self.role, 'Accountant', 'Lagi Student'))
        self.assertContains(self.client.get(self.role.get_absolute_url() + '?sent=1'), 'Thank you')

    def test_validation_and_honeypot(self):
        self.enable()
        r = self.client.post(self.url, {**self.data, 'email': 'not-an-email', 'consent': ''})
        self.assertEqual(r.status_code, 400)
        self.client.post(self.url, {**self.data, 'website': 'http://spam'})
        self.assertFalse(ExpressionOfInterest.objects.exists())

    def test_cannot_post_to_unpublished_or_mismatched_role(self):
        self.enable()
        self.assertEqual(self.client.post(reverse('career_connect_interest', args=['ah-liki-wholesale', 'sales', 'accountant']),
                                          self.data).status_code, 404)
        self.role.is_published = False
        self.role.save()
        self.assertEqual(self.client.post(self.url, self.data).status_code, 404)
        self.assertFalse(ExpressionOfInterest.objects.exists())

    def test_cannot_set_hidden_fields(self):
        self.enable()
        other = Role.objects.get(slug='welders')
        self.client.post(self.url, {**self.data, 'role': other.pk, 'reviewed': 'on', 'role_title': 'CEO'})
        eoi = ExpressionOfInterest.objects.get()
        self.assertEqual((eoi.role, eoi.role_title, eoi.reviewed), (self.role, 'Accountant', False))

    @override_settings(CAREER_CONNECT_INTEREST_LIMIT=2)
    def test_rate_limit(self):
        self.enable()
        for _ in range(3):
            r = self.client.post(self.url, self.data)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ExpressionOfInterest.objects.count(), 2)

    def test_csrf_enforced(self):
        self.enable()
        from django.test import Client
        r = Client(enforce_csrf_checks=True).post(self.url, self.data)
        self.assertEqual(r.status_code, 403)


class PublicImageTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def test_only_published_images_are_served(self):
        img = CompanyImage.objects.create(image=SimpleUploadedFile('hq.png', PNG, 'image/png'), caption='HQ')
        r = self.client.get(img.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/png')
        r.close()
        img.is_published = False
        img.save()
        self.assertEqual(self.client.get(img.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse('career_connect_image', args=[999])).status_code, 404)

    def test_media_folder_stays_private(self):
        img = CompanyImage.objects.create(image=SimpleUploadedFile('hq.png', PNG, 'image/png'))
        r = self.client.get('/media/' + img.image.name)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('login'), r['Location'])


def _all_url_patterns(patterns=None, prefix=''):
    for p in patterns if patterns is not None else get_resolver().url_patterns:
        if isinstance(p, URLResolver):
            yield from _all_url_patterns(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p


def _sample_path(route):
    """'shops/<int:shop_id>/' -> '/shops/1/'; regex routes get simple sample values."""
    path = re.sub(r'<int:\w+>', '1', route)
    path = re.sub(r'<(?:str|slug|path)?:?\w+>', 'x', path)
    path = re.sub(r'\(\?P<\w+>[^)]*\)', 'x', path).replace('^', '').replace('$', '').replace('\\', '')
    return '/' + path.lstrip('/')


class IsolationTests(TestCase):
    """Signed-out visitors (students) can't reach anything in the SMS, and the SMS keeps working as before."""

    def test_signed_out_visitor_cannot_open_any_private_route(self):
        self.maxDiff = None
        checked, open_routes = 0, []
        for route, pattern in _all_url_patterns():
            if pattern.name in PUBLIC_URL_NAMES or pattern.name in ('login', 'logout'):
                continue
            path = _sample_path(route)
            for method in ('get', 'post'):
                r = getattr(self.client, method)(path)
                ok = r.status_code in (302, 401, 403, 404, 405)
                if r.status_code == 302:
                    ok = 'login' in r['Location']   # sent to the SMS or admin sign-in, nowhere else
                if not ok:
                    open_routes.append(f'{method.upper()} {path} ({pattern.name}) gave {r.status_code}')
            checked += 1
        self.assertGreater(checked, 50)
        self.assertEqual(open_routes, [], 'open to signed-out visitors')

    def test_admin_and_management_need_sign_in(self):
        for url in (reverse('career_connect_manage_qr'), reverse('career_connect_manage_qr') + '?download=png',
                    '/admin/career_connect/portalsettings/1/change/', '/admin/career_connect/expressionofinterest/'):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn('login', r['Location'])

    def test_public_pages_do_not_start_a_session(self):
        self.client.get(reverse('career_connect'))
        self.assertNotIn('sessionid', self.client.cookies)

    def test_public_names_match_public_views(self):
        names = {p.name for route, p in _all_url_patterns()
                 if (p.name or '').startswith('career_connect') and not route.startswith('admin/')}
        self.assertEqual(names - PUBLIC_URL_NAMES, {'career_connect_manage_qr'})

    def test_existing_sign_in_still_works(self):
        _user('sione', 'Sales')
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        r = self.client.post(reverse('login'), {'username': 'sione', 'password': 'pw-123456'})
        self.assertRedirects(r, reverse('dashboard'), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_wrong_password_is_refused(self):
        _user('sione', 'Sales')
        r = self.client.post(reverse('login'), {'username': 'sione', 'password': 'wrong'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)

    def test_existing_access_levels_unchanged(self):
        sales = _user('sione', 'Sales')
        self.client.force_login(sales)
        self.assertEqual(self.client.get(reverse('reports')).status_code, 403)       # still blocked for Sales
        self.assertEqual(self.client.get('/admin/').status_code, 403)
        fe = _user('fe1', 'fe_boys')
        self.client.force_login(fe)
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('fe_home'), fetch_redirect_response=False)
        fin = _user('fin', 'Finance Staff')
        self.client.force_login(fin)
        self.assertEqual(self.client.get(reverse('shop_list')).status_code, 403)

    def test_signed_in_staff_of_every_level_can_open_the_portal(self):
        for name, group in (('s', 'Sales'), ('m', 'Marketing'), ('fe', 'fe_boys'), ('fin', 'Finance Staff')):
            self.client.force_login(_user(name, group))
            r = self.client.get(reverse('career_connect_role', args=['ah-liki-wholesale', 'finance', 'accountant']))
            self.assertEqual(r.status_code, 200, group)
            self.assertNotContains(r, 'Logout')
            # ...but not its management page
            r = self.client.get(reverse('career_connect_manage_qr'))
            self.assertIn(r.status_code, (302, 403), group)


class ManageQRTests(TestCase):
    def setUp(self):
        self.manager = _user('boss', 'Manager', is_staff=True)
        self.client.force_login(self.manager)

    def grant(self):
        self.manager.groups.add(Group.objects.get(name='Career Connect Admin'))

    def test_no_permission_by_default(self):
        self.assertFalse(Group.objects.get(name='Career Connect Admin').user_set.exists())
        self.assertFalse(self.manager.has_perm('career_connect.manage_career_connect'))
        self.assertEqual(self.client.get(reverse('career_connect_manage_qr')).status_code, 403)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Career Connect')
        self.assertEqual(self.client.get('/admin/career_connect/role/').status_code, 403)

    @override_settings(CAREER_CONNECT_URL='https://sms.ahliki.ws/career-connect/')
    def test_qr_page_and_downloads(self):
        self.grant()
        self.assertContains(self.client.get(reverse('dashboard')), reverse('career_connect_manage_qr'))
        r = self.client.get(reverse('career_connect_manage_qr'))
        self.assertContains(r, 'https://sms.ahliki.ws/career-connect/')
        self.assertNotContains(r, "Don't print")
        png = self.client.get(reverse('career_connect_manage_qr') + '?download=png')
        self.assertEqual(png['Content-Type'], 'image/png')
        self.assertIn('attachment', png['Content-Disposition'])
        self.assertTrue(png.content.startswith(b'\x89PNG'))
        svg = self.client.get(reverse('career_connect_manage_qr') + '?download=svg')
        self.assertIn(b'<svg', svg.content)
        self.assertEqual(self.client.get('/admin/career_connect/role/').status_code, 200)

    def test_qr_encodes_the_configured_public_url(self):
        url = 'https://sms.ahliki.ws/career-connect/'
        code = qr.make(url)
        self.assertEqual(code.designator.split('-')[1], 'M')
        # segno can't decode, so compare against a code built straight from the address
        import segno
        self.assertEqual(list(code.matrix), list(segno.make(url, error='m', micro=False).matrix))

    @override_settings(CAREER_CONNECT_URL='http://10.10.8.49:8000/career-connect/')
    def test_warns_about_development_address(self):
        self.grant()
        r = self.client.get(reverse('career_connect_manage_qr'))
        self.assertContains(r, "Don't print")
        self.assertContains(r, 'not an HTTPS address')
        self.assertContains(r, 'private/local network address')

    def test_url_checks(self):
        self.assertEqual(qr.url_problems('https://sms.ahliki.ws/career-connect/'), [])
        self.assertTrue(qr.url_problems('http://localhost:8000/career-connect/'))
        self.assertTrue(qr.url_problems('https://127.0.0.1/career-connect/'))
        self.assertTrue(qr.url_problems('https://sms.ahliki.ws/dashboard/'))

    def test_sales_user_with_group_still_cannot_download(self):
        """The SMS rule 'downloads are Managers only' still applies to the QR file."""
        sales = _user('sione', 'Sales', 'Career Connect Admin')
        self.client.force_login(sales)
        self.assertEqual(self.client.get(reverse('career_connect_manage_qr')).status_code, 200)
        self.assertEqual(self.client.get(reverse('career_connect_manage_qr') + '?download=png').status_code, 403)


class DesignTests(TestCase):
    """The home page layout: hero, coloured company cards, footer with the contact details."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def test_home_sections_and_links(self):
        p = PortalSettings.load()
        p.video_url = 'https://www.youtube.com/watch?v=qTc19B9_7iQ'
        p.save()
        r = self.client.get(reverse('career_connect'))
        for text in ('See Open Roles', 'href="#companies"', 'id="companies"', 'Companies of Ah Liki Investment',
                     'Watch Video', 'href="https://www.youtube.com/watch?v=qTc19B9_7iQ" target="_blank"'):
            self.assertContains(r, text)
        # One main page: no Home, About or Contact
        for text in ('>Home<', 'About Us', '>Contact<', 'Our Company', reverse('career_connect_about')):
            self.assertNotContains(r, text)
        p.video_url = ''
        p.save()
        self.assertNotContains(self.client.get(reverse('career_connect')), 'Watch Video')
        # Company cards, each with the number of published positions in its departments
        self.assertContains(r, '--c:#7C3AED')
        self.assertContains(r, '11 Available Positions')
        self.assertContains(r, '0 Available Positions')

    def test_photos_only_when_published(self):
        img = CompanyImage.objects.create(image=SimpleUploadedFile('hq.png', PNG, 'image/png'), is_published=False)
        p = PortalSettings.load()
        p.hero_image = p.company_image = img
        p.save()
        r = self.client.get(reverse('career_connect'))
        self.assertNotContains(r, img.get_absolute_url())
        self.assertContains(r, 'poster="/static/imgs/ahliki_building.png"')
        self.assertContains(r, '<source src="/static/videos/hero_video.mp4" type="video/mp4">')
        img.is_published = True
        img.save()
        r = self.client.get(reverse('career_connect'))
        self.assertContains(r, f'poster="{img.get_absolute_url()}"')

    def test_department_background_photo_faded_at_50_percent(self):
        dept = Department.objects.get(company__slug='ah-liki-wholesale', slug='trades')
        self.assertEqual(dept.background_opacity, 50)
        self.assertNotContains(self.client.get(reverse('career_connect')), 'dept-card has-photo')
        dept.background = SimpleUploadedFile('trades.png', PNG, 'image/png')
        dept.save()
        url = dept.image_url
        self.assertTrue(url.startswith(reverse('career_connect_department_image', args=['ah-liki-wholesale', 'trades']) + '?v='))
        for page in (dept.company.get_absolute_url(), dept.get_absolute_url()):
            r = self.client.get(page)
            self.assertContains(r, f"--photo:url('{url}');--photo-opacity:0.50;")
            self.assertContains(r, 'class="dept-card has-photo"' if page != dept.get_absolute_url() else 'dept has-photo')
        photo = self.client.get(url)
        self.assertEqual((photo.status_code, photo['Content-Type']), (200, 'image/png'))
        photo.close()
        # Signed out, the photo is only reachable through the portal while the department is published
        dept.is_published = False
        dept.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse('career_connect_department_image', args=['ah-liki-wholesale', 'finance'])).status_code, 404)
        self.assertEqual(self.client.get('/media/' + dept.background.name).status_code, 302)

    def test_company_can_use_its_own_uploaded_icon(self):
        c = Company.objects.get(slug='burger-bills')
        c.symbol = 'burger'   # one of the new icons
        c.save()
        self.assertContains(self.client.get(reverse('career_connect')), 'class="badge">')
        c.icon_image = SimpleUploadedFile('bb.png', PNG, 'image/png')
        c.save()
        url = c.icon_url
        self.assertTrue(url.startswith(reverse('career_connect_company_icon', args=['burger-bills']) + '?v='))
        for page in (reverse('career_connect'), c.get_absolute_url()):
            r = self.client.get(page)
            self.assertContains(r, f'<img class="icon-img" src="{url}"')
            self.assertContains(r, 'has-img')
        r = self.client.get(url)
        self.assertEqual((r.status_code, r['Content-Type']), (200, 'image/png'))
        r.close()
        self.assertEqual(self.client.get(reverse('career_connect_company_icon', args=['taula'])).status_code, 404)

    def test_admin_shows_the_icon_grid(self):
        self.client.force_login(User.objects.create_superuser('boss', 'boss@example.com', 'x'))
        c = Company.objects.get(slug='taula')
        r = self.client.get(reverse('admin:career_connect_company_change', args=[c.pk]))
        self.assertContains(r, 'class="cc-icon-grid"')
        self.assertContains(r, 'value="burger"')
        self.assertContains(r, 'name="icon_image"')
        self.assertContains(r, 'career_connect/admin_icons.css')
        d = Department.objects.filter(company=c).first() or Department.objects.first()
        self.assertContains(self.client.get(reverse('admin:career_connect_department_change', args=[d.pk])), 'cc-icon-grid')

    def test_company_logo_faded_behind_card_and_heading(self):
        c = Company.objects.get(slug='taula')
        self.assertEqual((c.background_opacity, c.background_fit), (50, 'contain'))
        self.assertNotContains(self.client.get(reverse('career_connect')), 'company-card has-photo')
        c.background = SimpleUploadedFile('taula.png', PNG, 'image/png')
        c.save()
        url = c.image_url
        self.assertTrue(url.startswith(reverse('career_connect_company_image', args=['taula']) + '?v='))
        for page in (reverse('career_connect'), c.get_absolute_url()):
            r = self.client.get(page)
            self.assertContains(r, f"--photo:url('{url}');--photo-opacity:0.50;")
            self.assertContains(r, 'dept has-photo fit-contain' if page == c.get_absolute_url()
                                else 'company-card has-photo fit-contain')
        c.background_fit = 'cover'
        c.save()
        self.assertContains(self.client.get(c.get_absolute_url()), 'dept has-photo fit-cover')
        photo = self.client.get(url)
        self.assertEqual((photo.status_code, photo['Content-Type']), (200, 'image/png'))
        photo.close()
        # Only while the company is published, and never for a company without a picture
        c.is_published = False
        c.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse('career_connect_company_image', args=['farmer-joe'])).status_code, 404)

    def test_every_company_has_the_wholesale_departments(self):
        wholesale = list(Department.objects.filter(company__slug='ah-liki-wholesale').values_list('slug', 'name'))
        self.assertEqual(len(wholesale), 6)
        for c in Company.objects.exclude(slug='ah-liki-wholesale'):
            self.assertEqual(list(c.departments.values_list('slug', 'name')), wholesale)
            self.assertFalse(Role.objects.filter(department__company=c).exists())
        r = self.client.get(reverse('career_connect_department', args=['farmer-joe', 'finance']))
        self.assertContains(r, 'Finance Department')

    def test_photo_strength_limits(self):
        from django.core.exceptions import ValidationError
        dept = Department.objects.get(company__slug='ah-liki-wholesale', slug='trades')
        dept.background_opacity = 95
        with self.assertRaises(ValidationError):
            dept.full_clean()
        dept.background_opacity = 70
        dept.full_clean()
        self.assertEqual(dept.photo_opacity, '0.70')

    def test_admin_can_upload_a_department_background(self):
        boss = _user('boss', 'Manager', 'Career Connect Admin', is_staff=True)
        self.client.force_login(boss)
        dept = Department.objects.get(company__slug='ah-liki-wholesale', slug='hr')
        change = reverse('admin:career_connect_department_change', args=[dept.pk])
        form = self.client.get(change)
        self.assertContains(form, 'name="background"')
        self.assertContains(form, 'name="background_opacity"')
        self.assertContains(form, 'value="50"')
        self.assertContains(form, 'Preview (after saving)')
        data = {'company': dept.company_id, 'name': dept.name, 'slug': dept.slug, 'symbol': dept.symbol, 'colour': dept.colour, 'description': '',
                'order': dept.order, 'is_published': 'on', 'background_opacity': 50,
                'background': SimpleUploadedFile('hr.png', PNG, 'image/png'),
                'roles-TOTAL_FORMS': 0, 'roles-INITIAL_FORMS': 0, 'roles-MIN_NUM_FORMS': 0, 'roles-MAX_NUM_FORMS': 1000}
        r = self.client.post(change, data)
        self.assertEqual(r.status_code, 302, re.findall(r'errorlist[^>]*>(.*?)</ul>', r.content.decode(), re.S))
        dept.refresh_from_db()
        self.assertTrue(dept.background.name.startswith('career_connect/departments/hr'))
        self.assertContains(self.client.get(change), 'opacity:0.50')
        # A non-image is refused
        data['background'] = SimpleUploadedFile('notes.txt', b'hello', 'text/plain')
        self.assertEqual(self.client.post(change, data).status_code, 200)

    def test_social_icons_only_when_set(self):
        self.assertNotContains(self.client.get(reverse('career_connect')), 'class="social"')
        p = PortalSettings.load()
        p.facebook_url, p.footer_slogan = 'https://www.facebook.com/example', 'Building People | Growing Futures'
        p.save()
        r = self.client.get(reverse('career_connect'))
        self.assertContains(r, 'href="https://www.facebook.com/example"')
        self.assertContains(r, 'aria-label="Ah Liki Wholesale on Facebook"')
        self.assertNotContains(r, 'on Instagram')
        self.assertContains(r, 'Building People | Growing Futures')


class HRVacancyTests(TestCase):
    """HR: post and update vacancies for every company, and nothing else of the SMS."""

    def setUp(self):
        self.hr = _user('hr', 'HR')
        self.client.force_login(self.hr)
        self.fj_finance = Department.objects.get(company__slug='farmer-joe', slug='finance')

    def _tomorrow(self):
        import datetime
        from .models import office_today
        return (office_today() + datetime.timedelta(days=1)).isoformat()

    def _post(self, **extra):
        data = {'place': f'd{self.fj_finance.pk}', 'title': 'Accounts Assistant', 'summary': 'Daily bookkeeping',
                'expires_on': self._tomorrow(), 'responsibilities': 'Invoices\nReconciliations', 'qualifications': '',
                'skills': '', 'apply_method': Role.APPLY_NONE, 'apply_email': '', 'apply_url': '',
                'how_to_apply': '', 'is_published': 'on', **extra}
        return self.client.post(reverse('hr_vacancy_add'), data)

    def test_group_has_only_the_vacancy_permission(self):
        group = Group.objects.get(name='HR')
        self.assertEqual(list(group.permissions.values_list('codename', flat=True)), ['manage_vacancies'])
        self.assertTrue(Group.objects.get(name='Career Connect Admin').permissions.filter(codename='manage_vacancies').exists())

    def test_sign_in_lands_on_vacancies_and_the_rest_of_the_sms_is_closed(self):
        r = self.client.get(reverse('dashboard'))
        self.assertRedirects(r, reverse('hr_vacancies'))
        r = self.client.get(reverse('hr_vacancies'))
        self.assertContains(r, 'Human Resources')
        self.assertNotContains(r, 'All Clients')
        self.assertNotContains(r, 'Car Allocations')
        for url in (reverse('shop_list'), reverse('car_allocations'), reverse('career_connect_manage_qr'), '/admin/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.get(reverse('career_connect')).status_code, 200)

    def test_every_company_and_department_can_be_chosen(self):
        r = self.client.get(reverse('hr_vacancy_add'))
        for c in Company.objects.all():
            self.assertContains(r, f'<optgroup label="{c.name}">')
        self.assertContains(r, f'value="d{self.fj_finance.pk}"')
        for c in Company.objects.all():   # every company can take a position without a department
            self.assertContains(r, f'value="c{c.pk}"')

    def test_post_a_vacancy_without_a_department(self):
        taula = Company.objects.get(slug='taula')
        r = self._post(place=f'c{taula.pk}', title='Store Supervisor')
        self.assertRedirects(r, reverse('hr_vacancies'))
        role = Role.objects.get(title='Store Supervisor')
        self.assertEqual((role.company, role.department, role.place), (taula, None, 'Taula'))
        self.assertEqual(role.get_absolute_url(), '/career-connect/careers/taula/roles/store-supervisor/')
        # Listed on the company page, which opens straight to it, and on the main page's open positions
        company_page = self.client.get(taula.get_absolute_url())
        self.assertContains(company_page, 'Open positions')
        self.assertContains(company_page, f'href="{role.get_absolute_url()}"')
        self.assertContains(self.client.get(reverse('career_connect')), f'href="{role.get_absolute_url()}"')
        page = self.client.get(role.get_absolute_url())
        self.assertContains(page, 'Store Supervisor')
        self.assertContains(page, '<div class="kicker">Taula</div>')
        # Counted on the company card, and the HR list shows it under the company
        self.assertContains(self.client.get(reverse('career_connect')), '1 Available Position<')
        self.assertContains(self.client.get(reverse('hr_vacancies')), 'No department')
        # Moving it into a department gives it the department address
        dept = Department.objects.create(company=taula, name='Retail', slug='retail')
        r = self.client.post(reverse('hr_vacancy_edit', args=[role.pk]), {
            'place': f'd{dept.pk}', 'title': 'Store Supervisor', 'expires_on': self._tomorrow(),
            'apply_method': Role.APPLY_NONE, 'is_published': 'on'})
        self.assertRedirects(r, reverse('hr_vacancies'))
        role.refresh_from_db()
        self.assertEqual(role.get_absolute_url(), '/career-connect/careers/taula/retail/store-supervisor/')

    def test_interest_form_for_a_role_without_a_department(self):
        taula = Company.objects.get(slug='taula')
        role = Role.objects.create(company=taula, title='Cashier', slug='cashier', apply_method=Role.APPLY_FORM)
        self.assertEqual(role.interest_url, '/career-connect/careers/taula/roles/cashier/interest/')
        self.client.logout()
        r = self.client.post(role.interest_url, {'full_name': 'Lagi', 'email': 'lagi@example.com', 'consent': 'on'})
        self.assertRedirects(r, role.get_absolute_url() + '?sent=1#apply', fetch_redirect_response=False)
        self.assertEqual(role.interests.count(), 1)

    def test_department_role_and_company_must_match(self):
        from django.core.exceptions import ValidationError
        role = Role(company=Company.objects.get(slug='taula'), department=self.fj_finance, title='X', slug='x')
        with self.assertRaises(ValidationError):
            role.full_clean()
        role.save()   # saving always follows the department
        self.assertEqual(role.company.slug, 'farmer-joe')

    def test_post_a_vacancy_for_another_company(self):
        r = self._post()
        self.assertRedirects(r, reverse('hr_vacancies'))
        role = Role.objects.get(department=self.fj_finance)
        self.assertEqual((role.slug, role.vacancy_status, role.is_published), ('accounts-assistant', Role.OPEN, True))
        self.assertContains(self.client.get(self.fj_finance.get_absolute_url()), 'Accounts Assistant')
        page = self.client.get(role.get_absolute_url())
        self.assertContains(page, 'Invoices')
        # Same title again in the same department gets its own address
        self._post()
        self.assertEqual(sorted(Role.objects.filter(department=self.fj_finance).values_list('slug', flat=True)),
                         ['accounts-assistant', 'accounts-assistant-2'])
        listing = self.client.get(reverse('hr_vacancies'), {'company': 'farmer-joe'})
        self.assertContains(listing, 'class="hr-title"', count=2)
        self.assertNotContains(listing, 'Welders')

    def test_apply_button_needs_its_address(self):
        r = self._post(apply_method=Role.APPLY_EMAIL)
        self.assertContains(r, 'Enter the email address applications should go to.')
        self.assertFalse(Role.objects.filter(department=self.fj_finance).exists())

    def test_edit_status_and_remove(self):
        self._post()
        role = Role.objects.get(department=self.fj_finance)
        r = self.client.post(reverse('hr_vacancy_edit', args=[role.pk]), {
            'place': f'd{self.fj_finance.pk}', 'title': 'Senior Accounts Assistant', 'expires_on': self._tomorrow(),
            'apply_method': Role.APPLY_NONE, 'is_published': 'on'})
        self.assertRedirects(r, reverse('hr_vacancies'))
        role.refresh_from_db()
        self.assertEqual((role.title, role.slug), ('Senior Accounts Assistant', 'accounts-assistant'))
        status = reverse('hr_vacancy_status', args=[role.pk])
        self.client.post(status, {'action': 'hide'})
        role.refresh_from_db()
        self.assertEqual((role.recruiting_status, role.is_published), (Role.OPEN, False))
        self.assertEqual(self.client.get(role.get_absolute_url()).status_code, 404)
        # Never sent back to another site
        r = self.client.post(status, {'action': 'publish', 'next': 'https://evil.example/'})
        self.assertRedirects(r, reverse('hr_vacancies'))
        r = self.client.post(reverse('hr_vacancy_delete', args=[role.pk]), {'next': reverse('hr_vacancies') + '?status=draft'})
        self.assertRedirects(r, reverse('hr_vacancies') + '?status=draft')
        self.assertFalse(Role.objects.filter(pk=role.pk).exists())
        self.assertEqual(self.client.get(status).status_code, 405)

    def test_others_cannot_use_the_hr_pages(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('hr_vacancies')), reverse('login') + '?next=' + reverse('hr_vacancies'),
                             fetch_redirect_response=False)
        self.client.force_login(_user('sales', 'Sales'))
        self.assertEqual(self.client.get(reverse('hr_vacancies')).status_code, 403)
        self.client.force_login(_user('boss', is_superuser=True))
        r = self.client.get(reverse('hr_vacancies'))
        self.assertContains(r, 'Welders')
        self.assertContains(r, 'href="' + reverse('hr_vacancies') + '"')

    def test_position_comes_off_career_connect_on_its_expiry_date(self):
        import datetime
        from .models import office_today
        today = office_today()
        role = Role.objects.get(department__company__slug='ah-liki-wholesale', slug='welders')
        role.expires_on = today + datetime.timedelta(days=1)
        role.save()
        self.assertContains(self.client.get(role.get_absolute_url()), 'Closes')
        self.assertContains(self.client.get(role.department.get_absolute_url()), 'Welders')
        careers = reverse('career_connect')
        self.assertContains(self.client.get(careers), '11 Available Positions')
        # On the expiry date it disappears everywhere students look, and HR sees it as expired
        Role.objects.filter(pk=role.pk).update(expires_on=today)
        self.assertEqual(self.client.get(role.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(role.department.get_absolute_url()), 'Welders')
        self.assertContains(self.client.get(careers), '10 Available Positions')
        listing = self.client.get(reverse('hr_vacancies'), {'status': 'expired'})
        self.assertContains(listing, 'class="hr-title"', count=1)
        self.assertContains(listing, 'badge-red">Expired')

    def test_expiry_date_is_required_and_status_is_not_on_the_form(self):
        r = self._post(expires_on='')
        self.assertContains(r, 'This field is required.')
        self.assertNotContains(r, 'name="vacancy_status"')
        self.assertFalse(Role.objects.filter(department=self.fj_finance).exists())

    def test_expiry_date_must_be_after_today(self):
        from .models import office_today
        r = self._post(expires_on=office_today().isoformat())
        self.assertContains(r, 'Choose a date after today')
        self.assertFalse(Role.objects.filter(department=self.fj_finance).exists())

    def test_expiry_date_sets_the_recruiting_status(self):
        import datetime
        from .models import office_today
        tomorrow = office_today() + datetime.timedelta(days=1)
        # Saved as 'not recruiting' with a date: it's recruiting until the date
        self._post(vacancy_status=Role.CLOSED, expires_on=tomorrow.isoformat())
        role = Role.objects.get(department=self.fj_finance)
        self.assertEqual((role.vacancy_status, role.recruiting_status), (Role.OPEN, Role.OPEN))
        self.assertContains(self.client.get(role.get_absolute_url()), 'Currently recruiting')
        listing = self.client.get(reverse('hr_vacancies'), {'company': 'farmer-joe', 'status': Role.OPEN})
        self.assertContains(listing, '● Recruiting')
        # The quick status actions don't apply while a date is set
        self.assertNotContains(listing, 'name="action" value="closed"')
        self.client.post(reverse('hr_vacancy_status', args=[role.pk]), {'action': 'closed'})
        role.refresh_from_db()
        self.assertEqual(role.recruiting_status, Role.OPEN)
        # Once due: not currently recruiting
        Role.objects.filter(pk=role.pk).update(expires_on=office_today())
        role.refresh_from_db()
        self.assertEqual((role.recruiting_status, role.recruiting_status_label), (Role.CLOSED, 'Not currently recruiting'))
        listing = self.client.get(reverse('hr_vacancies'), {'company': 'farmer-joe', 'status': Role.CLOSED})
        self.assertContains(listing, 'class="hr-title"', count=1)
        self.assertContains(listing, 'Not recruiting')
        # Without a date, HR's own choice stands
        self.assertEqual(Role.objects.get(department__company__slug='ah-liki-wholesale', slug='welders').recruiting_status,
                         Role.NOT_STATED)

    def test_new_vacancy_defaults_to_the_email_apply_button(self):
        p = PortalSettings.load()
        p.contact_email = 'careers@ahliki.com'
        p.save()
        form = self.client.get(reverse('hr_vacancy_add')).context['form']
        self.assertEqual((form['apply_method'].value(), form['apply_email'].value()),
                         (Role.APPLY_EMAIL, 'careers@ahliki.com'))
        # Editing keeps the position's own choice
        self._post()
        role = Role.objects.get(department=self.fj_finance)
        form = self.client.get(reverse('hr_vacancy_edit', args=[role.pk])).context['form']
        self.assertEqual(form['apply_method'].value(), Role.APPLY_NONE)
