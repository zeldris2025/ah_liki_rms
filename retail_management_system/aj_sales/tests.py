from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import report
from .csv_import import import_qty_sales
from .models import QtySales


def user(name, *groups, **extra):
    u = User.objects.create_user(name, password='x', **extra)
    for g in groups:
        u.groups.add(Group.objects.get_or_create(name=g)[0])
    return u


def upload(text):
    return SimpleUploadedFile('qty.csv', text.encode('utf-8'), content_type='text/csv')


def sale(product, month, qty, name=''):
    return QtySales.objects.create(product_code=product, product_name=name or product, month=month, qty=qty)


class ImportTests(TestCase):
    def test_adds_then_replaces_instead_of_doubling(self):
        csv = 'Product Code,Product Name,Month,QTY\nP1,Milk,2026-09,120\n'
        r = import_qty_sales(upload(csv))
        self.assertEqual(r['created'], 1)
        r = import_qty_sales(upload(csv.replace('120', '"1,250"')))
        self.assertEqual((r['created'], r['updated']), (0, 1))
        self.assertEqual(QtySales.objects.get().qty, Decimal('1250'))

    def test_rows_for_the_same_month_are_added_together(self):
        r = import_qty_sales(upload('Product Code,Month,QTY\nP1,26-09,10\np1,Sep-26,5\n'))
        self.assertEqual(r['combined'], 1)
        self.assertEqual(QtySales.objects.get().qty, 15)

    def test_header_aliases(self):
        import_qty_sales(upload('Item Code,Description,Period,Quantity\nP1,Milk,2025-01,7\n'))
        row = QtySales.objects.get()
        self.assertEqual((row.product_code, row.product_name, row.qty), ('P1', 'Milk', 7))

    def test_bad_rows_are_skipped(self):
        r = import_qty_sales(upload('Product Code,Month,QTY\nP1,nope,5\nP2,2026-01,lots\n,2026-01,3\nP3,2026-01,4\n'))
        self.assertEqual((r['created'], len(r['skipped'])), (1, 3))

    def test_missing_columns(self):
        from shops.client_import import ImportFileError
        with self.assertRaises(ImportFileError):
            import_qty_sales(upload('Product Code,QTY\nP1,5\n'))


class ReportTests(TestCase):
    def setUp(self):
        sale('P1', date(2026, 1, 1), 100)
        sale('P1', date(2026, 2, 1), 50)
        sale('P2', date(2026, 2, 1), 30)
        sale('P1', date(2025, 1, 1), 80)
        sale('P1', date(2025, 2, 1), 20)
        sale('P1', date(2025, 11, 1), 999)   # after Feb, so not in this year to date

    def test_year_to_date_compares_the_same_months(self):
        f = report.read_filters({})
        self.assertEqual((f['year'], f['compare'], f['months']), (2026, 2025, [1, 2]))
        rows = report.compare_rows(report.scope(f), f)
        s = report.summary(report.scope(f), f, rows)
        self.assertEqual((s['this'], s['last']), (180, 100))
        self.assertEqual(s['change']['pct'], 80.0)
        p1, p2 = rows
        self.assertEqual((p1['code'], p1['this'], p1['last'], p1['change']['pct']), ('P1', 150, 100, 50.0))
        self.assertTrue(p2['is_new'])

    def test_full_year_and_one_month(self):
        f = report.read_filters({'period': 'full'})
        self.assertEqual(report.total(report.in_period(report.scope(f), f, 2025)), 1099)
        f = report.read_filters({'period': '2', 'product': 'p1'})
        self.assertEqual(report.total(report.in_period(report.scope(f), f, 2026)), 50)


@override_settings(OFFICE365={})
class AccessTests(TestCase):
    def setUp(self):
        self.aj = user('aj', 'Product QTY Sales')
        self.manager = user('boss', 'Manager')
        self.sales = user('sione', 'Sales')
        sale('P1', date(2026, 1, 1), 100, 'Milk')
        sale('P1', date(2025, 1, 1), 80, 'Milk')
        sale('P2', date(2026, 1, 1), 60, 'Bread')

    def test_the_group_exists(self):
        self.assertTrue(Group.objects.filter(name='Product QTY Sales').exists())

    def test_aj_get_their_dashboard_and_menu(self):
        self.client.force_login(self.aj)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'QTY Sales Dashboard')
        for tab in ('Dashboard', 'Analytics', 'Product QTY', 'Import CSV'):
            self.assertContains(r, tab)
        self.assertNotContains(r, 'All Clients')
        self.assertNotContains(r, 'Car Allocations')
        self.assertEqual(r.context['user_role'], 'Product QTY Sales')

    def test_aj_only_open_their_pages(self):
        self.client.force_login(self.aj)
        for name in ('aj_analytics', 'aj_product_qty', 'aj_import'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for name in ('shop_list', 'analytics', 'monthly_sales', 'atlas', 'car_allocations', 'social_numbers'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get('/admin/').status_code, 403)

    def test_the_chart_on_top_follows_the_quick_link(self):
        self.client.force_login(self.aj)
        r = self.client.get(reverse('aj_product_qty'))
        self.assertEqual((r.context['trend']['title'], r.context['trend']['this'][0]), ('All products', 160.0))
        self.assertNotContains(r, 'Head to head')
        r = self.client.get(reverse('aj_product_qty') + '?product=p1')
        t = r.context['trend']
        self.assertEqual((t['title'], t['this'][0], t['last'][0], t['has_target']), ('Milk', 100.0, 80.0, False))

    def test_aj_can_export_csv(self):
        self.client.force_login(self.aj)
        for url in (reverse('aj_product_qty') + '?export=1', reverse('aj_product_qty') + '?view=rows&export=1',
                    reverse('aj_analytics') + '?export=monthly', reverse('aj_analytics') + '?export=products',
                    reverse('aj_template')):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertIn('attachment', r['Content-Disposition'])
        body = self.client.get(reverse('aj_product_qty') + '?export=1').content.decode('utf-8-sig')
        self.assertIn('QTY 2025,QTY 2026', body)
        self.assertIn('P1,Milk,80,100,20,+25.0%', body)

    def test_aj_can_upload(self):
        self.client.force_login(self.aj)
        r = self.client.post(reverse('aj_import'), {'csv_file': upload('Product Code,Month,QTY\nP9,2026-03,4\n')})
        self.assertEqual(r.context['result']['created'], 1)

    def test_managers_see_it_and_sales_dont(self):
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse('dashboard')), 'Product QTY Sales')
        self.assertEqual(self.client.get(reverse('aj_analytics') + '?product=p1').status_code, 200)
        self.client.force_login(self.sales)
        self.assertEqual(self.client.get(reverse('aj_product_qty')).status_code, 403)


class AdminFastDeleteTests(TestCase):
    def test_deletes_thousands_of_rows_in_one_go(self):
        QtySales.objects.bulk_create(QtySales(product_code=f'P{i}', month=date(2025, 1 + i % 12, 1), qty=1)
                                     for i in range(4000))
        sale('KEEP', date(2026, 1, 1), 5)
        self.client.force_login(User.objects.create_superuser('admin', password='x'))
        url = reverse('admin:aj_sales_qtysales_changelist') + '?year=2025'
        data = {'action': 'fast_delete', 'select_across': '1', '_selected_action': ['1'], 'index': '0'}
        confirm = self.client.post(url, data)
        self.assertContains(confirm, '4,000')
        self.client.post(url, {**data, 'post': 'yes'})
        self.assertEqual(list(QtySales.objects.values_list('product_code', flat=True)), ['KEEP'])


@override_settings(OFFICE365={})
class QuickLinkTests(TestCase):
    """Pinned products and groups on Product QTY, measured against last year's QTY (or a target set by hand)."""
    def setUp(self):
        from .models import QtyProductGroup
        self.client.force_login(user('aj', 'Product QTY Sales'))
        for code, name, q25, q26 in (('TT1', 'Tip Top Vanilla', 100, 120), ('TT2', 'Tip Top Choc', 100, 60),
                                     ('CK1', 'Coke 1.5L', 50, 40)):
            sale(code, date(2025, 3, 1), q25, name)
            sale(code, date(2026, 3, 1), q26, name)
        self.group = QtyProductGroup.objects.create(name='Tip Top', keywords='tip top')
        self.url = reverse('aj_product_qty') + '?year=2026&lm=3'

    def test_pin_and_unpin(self):
        from .models import QtyPinnedProduct
        self.client.post(reverse('aj_pin'), {'code': 'ck1', 'next': self.url})
        self.assertEqual(list(QtyPinnedProduct.objects.values_list('product_code', flat=True)), ['CK1'])
        self.client.post(reverse('aj_pin'), {'code': 'CK1'})
        self.assertFalse(QtyPinnedProduct.objects.exists())
        self.client.post(reverse('aj_pin'), {'code': 'NOPE'})   # no QTY uploaded, so not pinned
        self.assertFalse(QtyPinnedProduct.objects.exists())

    def test_targets_default_to_last_year_and_colour_the_links(self):
        from .models import QtyPinnedProduct
        QtyPinnedProduct.objects.create(product_code='CK1')
        r = self.client.get(self.url)
        links = {q['name']: q for q in r.context['quick']['links']}
        self.assertEqual((links['Tip Top']['month_qty'], links['Tip Top']['target'], links['Tip Top']['pct']), (180, 200, 90))
        self.assertEqual(links['Tip Top']['status'], 'close')
        self.assertEqual((links['Coke 1.5L']['pct'], links['Coke 1.5L']['status']), (80, 'close'))
        self.assertContains(r, '★ Quick links')

    def test_targets_set_by_hand(self):
        from .models import QtyTarget
        r = self.client.post(reverse('aj_targets') + '?year=2026', {f'g{self.group.pk}_3': '150', f'g{self.group.pk}_4': 'lots'})
        self.assertContains(r, 'is not a number')
        self.assertFalse(QtyTarget.objects.exists())   # nothing saved until every box is right
        self.client.post(reverse('aj_targets') + '?year=2026', {f'g{self.group.pk}_3': '150'})
        link = self.client.get(self.url).context['quick']['links'][0]
        self.assertEqual((link['target'], link['manual_target'], link['pct'], link['status']), (150, True, 120, 'good'))

    def test_group_form_and_filter(self):
        from .models import QtyProductGroup
        self.assertEqual(self.client.get(reverse('aj_group_add')).status_code, 200)
        r = self.client.post(reverse('aj_group_add'), {'name': 'Mixed', 'keywords': '', 'product_codes': 'ck1\ntt2'})
        g = QtyProductGroup.objects.get(name='Mixed')
        self.assertEqual(g.code_list(), ['CK1', 'TT2'])
        page = self.client.get(reverse('aj_product_qty') + f'?group={g.pk}')
        self.assertEqual(sorted(r['code'] for r in page.context['page_obj']), ['CK1', 'TT2'])
        self.assertEqual(self.client.post(reverse('aj_group_edit', args=[g.pk]), {'name': 'Mixed', 'keywords': ''}).status_code, 200)   # needs a rule
        self.client.post(reverse('aj_group_edit', args=[g.pk]), {'delete': '1'})
        self.assertFalse(QtyProductGroup.objects.filter(name='Mixed').exists())

    def test_quick_links_on_analytics_filter_the_page(self):
        r = self.client.get(reverse('aj_analytics') + '?year=2026&lm=3')
        self.assertContains(r, '★ Quick links')
        self.assertEqual(r.context['summary']['this'], 220)
        r = self.client.get(reverse('aj_analytics') + f'?year=2026&group={self.group.pk}')
        self.assertContains(r, '🗂 Tip Top')
        self.assertEqual((r.context['summary']['this'], r.context['summary']['last']), (180, 200))
        self.assertEqual(r.context['chart']['monthly']['this'][2], 180.0)
