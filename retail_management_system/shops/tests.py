from decimal import Decimal
import csv
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Promotion


def _manager(username):
    """An office user with the Manager access level (full access), as most of these tests expect."""
    from django.contrib.auth.models import Group
    user = User.objects.create_user(username, password='pw')
    user.groups.add(Group.objects.get(name='Manager'))
    return user


def _days(n):
    return date.today() + timedelta(days=n)


class PromotionTests(TestCase):
    def setUp(self):
        self.user = _manager('office')
        self.client.login(username='office', password='pw')

    def test_status_follows_dates(self):
        upcoming = Promotion.objects.create(name='Soon', company='Taula', start_date=_days(5), end_date=_days(20))
        active   = Promotion.objects.create(name='Now', company='Taula', start_date=_days(-5), end_date=_days(5))
        ended    = Promotion.objects.create(name='Done', company='Taula', start_date=_days(-20), end_date=_days(-1))
        open_end = Promotion.objects.create(name='Ongoing', company='Taula')
        self.assertEqual([p.status for p in (upcoming, active, ended, open_end)],
                         ['Upcoming', 'Active', 'Ended', 'Active'])
        for status, expected in (('Upcoming', {'Soon'}), ('Active', {'Now', 'Ongoing'}), ('Ended', {'Done'})):
            names = set(Promotion.objects.filter(Promotion.status_q(status)).values_list('name', flat=True))
            self.assertEqual(names, expected, status)

    def test_add_edit_delete(self):
        self.client.post(reverse('add_promotion'), {
            'name': 'Teuila Draw', 'company': 'Taula', 'details': 'Buy a 6-pack to enter',
            'prizes': '1st — VIP passes\n2nd — Merch pack', 'start_date': '2026-10-01', 'end_date': '2026-10-31',
        })
        promo = Promotion.objects.get()
        self.assertEqual((promo.company, promo.prize_list, promo.end_date),
                         ('Taula', ['1st — VIP passes', '2nd — Merch pack'], date(2026, 10, 31)))

        page = self.client.get(reverse('promotion_list')).content.decode()
        self.assertIn('Teuila Draw', page)
        self.assertIn(reverse('edit_promotion', args=[promo.pk]), page)

        self.client.post(reverse('edit_promotion', args=[promo.pk]), {
            'name': 'Teuila Draw', 'company': 'Taula', 'details': '', 'prizes': '',
            'start_date': '2026-10-01', 'end_date': '2026-11-15',
        })
        promo.refresh_from_db()
        self.assertEqual((promo.end_date, promo.prizes), (date(2026, 11, 15), ''))

        self.client.post(reverse('edit_promotion', args=[promo.pk]), {'delete_promotion': '1'})
        self.assertFalse(Promotion.objects.exists())

    def test_form_rejects_bad_input(self):
        response = self.client.post(reverse('add_promotion'), {
            'name': '', 'company': 'Nobody', 'start_date': '2026-10-10', 'end_date': '2026-10-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['errors']), 3)
        self.assertFalse(Promotion.objects.exists())

    def test_report_columns(self):
        Promotion.objects.create(name='Stamp Card', company='Burger Bills', prizes='Free burger')
        csv_text = self.client.get(reverse('download_report') + '?type=promotions').content.decode()
        self.assertTrue(csv_text.startswith('ID,Promotion Name,Company,Details,Prizes,Start Date,End Date,Status'))
        self.assertIn('Stamp Card,Burger Bills,,Free burger,,,Active', csv_text)


class PromotionImportTests(TestCase):
    def _import(self, csv_text, dry_run=False):
        from tablib import Dataset
        from .admin import PromotionResource
        return PromotionResource().import_data(Dataset().load(csv_text, format='csv'), dry_run=dry_run)

    def test_import_creates_and_updates_by_company_and_name(self):
        Promotion.objects.create(name='Stamp Card', company='Burger Bills', details='old')
        result = self._import(
            'Promotion Name,Company,Details,Prizes,Start Date,End Date\n'
            'Stamp Card,burger bills,New details,Free burger,2026-10-01,31/12/2026\n'
            'Teuila Draw,Taula,Buy a 6-pack,"1st — VIP passes\n2nd — Merch",01/10/2026,\n')
        self.assertFalse(result.has_errors() or result.has_validation_errors())
        self.assertEqual(Promotion.objects.count(), 2)
        stamp = Promotion.objects.get(name='Stamp Card')
        self.assertEqual((stamp.details, stamp.prizes, stamp.start_date, stamp.end_date),
                         ('New details', 'Free burger', date(2026, 10, 1), date(2026, 12, 31)))
        teuila = Promotion.objects.get(name='Teuila Draw')
        self.assertEqual((teuila.prize_list, teuila.start_date, teuila.end_date),
                         (['1st — VIP passes', '2nd — Merch'], date(2026, 10, 1), None))

    def test_import_rejects_unknown_company_and_bad_date(self):
        result = self._import('Promotion Name,Company,Start Date\n'
                              'Mystery,Coca Cola,2026-10-01\n'
                              'Bad Date,Taula,next week\n')
        self.assertTrue(result.has_validation_errors())
        self.assertEqual(len(result.invalid_rows), 2)
        self.assertFalse(Promotion.objects.exists())

    def test_admin_import_page_loads(self):
        User.objects.create_superuser('admin', password='pw')
        self.client.login(username='admin', password='pw')
        self.assertEqual(self.client.get(reverse('admin:shops_promotion_import')).status_code, 200)
        self.assertContains(self.client.get(reverse('admin:shops_promotion_changelist')), 'Import')


class DashboardTests(TestCase):
    def test_dashboard_shows_orders_promotions_and_alerts(self):
        from fe_orders.models import Order, OrderItem, Product
        from .models import Shop
        user = _manager('office')
        self.client.login(username='office', password='pw')
        shop = Shop.objects.create(name='Jane Store', territory='EC2')
        coke = Product.objects.create(name='Coke', category='Soda', unit_price='10.00')
        Product.objects.create(name='Water', category='Water', available=False)
        order = Order.objects.create(shop=shop, placed_by=user, telegram_status='Failed: chat not found')
        OrderItem.objects.create(order=order, product=coke, quantity=3, unit_price='10.00')
        Promotion.objects.create(name='Live Deal', company='Taula', start_date=_days(-1), end_date=_days(10),
                                 prizes='Merch pack')
        Promotion.objects.create(name='Next Deal', company='Taula', start_date=_days(5))
        Promotion.objects.create(name='Old Deal', company='Taula', end_date=_days(-3))

        response = self.client.get(reverse('dashboard'))
        ctx = response.context
        self.assertEqual((ctx['pending_orders'], ctx['orders_today'], ctx['telegram_failed'], ctx['out_of_stock']),
                         (1, 1, 1, 1))
        self.assertEqual([p.name for p in ctx['dashboard_promos']], ['Live Deal', 'Next Deal'])
        page = response.content.decode()
        for text in ('All Clients', 'Corporate Sales', 'Jane Store', '3 units', 'didn’t reach Telegram',
                     '1 of 2 products out of stock', 'Live Deal', '🏆 1', 'Next Deal', 'Clients by Territory'):
            self.assertIn(text, page)
        self.assertNotIn('Old Deal', page)


class ClientImportTests(TestCase):
    HEADER = 'Customer Code,Name,Customer Type,Contact Person,Address,Island,Phone Number,Territory Code,Email\n'

    def setUp(self):
        _manager('office')
        self.client.login(username='office', password='pw')

    def upload(self, text, url='import_shops'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('c.csv', text.encode('utf-8-sig'), content_type='text/csv')
        response = self.client.post(reverse(url), {'csv_file': f})
        return response.context.get('result') or response.context.get('error')

    def test_same_file_every_day_is_safe(self):
        from .models import Shop
        text = (self.HEADER +
                'C001,Jane Store,Retail,Sione,Lalovaea,upolu,7771234,ec2,JANE@EXAMPLE.COM\n'
                'C002,Sam Mart,Wholesale,Tavita,Salelologa,SAVAII,7770000,SAV,\n')
        first = self.upload(text)
        self.assertEqual((first['created'], first['updated'], first['unchanged'], first['skipped']), (2, 0, 0, []))
        jane = Shop.objects.get(customer_code='C001')
        self.assertEqual((jane.island, jane.territory, jane.email, jane.contact_person),
                         ('Upolu', 'EC2', 'jane@example.com', 'Sione'))
        self.assertEqual(Shop.objects.get(customer_code='C002').island, 'Savaii')

        again = self.upload(text)
        self.assertEqual((again['created'], again['updated'], again['unchanged'], again['skipped']), (0, 0, 2, []))
        self.assertEqual(Shop.objects.count(), 2)

    def test_code_is_required_and_a_known_code_updates_the_name(self):
        from .models import Shop
        Shop.objects.create(customer_code='C001', name='Jane Store', phone='111', contact_person='Old', email='a@b.ws')
        result = self.upload(self.HEADER +
                             'C001,  Jane Store & Bakery ,,New Person,,,222,,\n'   # renamed in the office system
                             ',Somebody Else,,,,,999,,\n'                           # no code: rejected
                             'C002,,,,,,,,\n')                                      # new code without a name
        self.assertEqual((result['updated'], result['created'], len(result['skipped'])), (1, 0, 2))
        self.assertEqual(result['renamed'], ['C001: “Jane Store” → “Jane Store & Bakery”'])
        self.assertIn('Customer Code is required', result['skipped'][0])
        self.assertIn('new code C002 needs a Name', result['skipped'][1])
        jane = Shop.objects.get(customer_code='C001')
        self.assertEqual((jane.name, jane.phone, jane.contact_person, jane.email), ('Jane Store & Bakery', '222', 'New Person', 'a@b.ws'))
        self.assertEqual(Shop.objects.count(), 1)
        again = self.upload(self.HEADER + 'C001,Jane Store & Bakery,,,,,,,\nC001,,,,,,333,,\n')   # blank name keeps it
        self.assertEqual((again['renamed'], again['unchanged'], again['updated']), ([], 1, 1))
        self.assertEqual(Shop.objects.get(customer_code='C001').name, 'Jane Store & Bakery')

    def test_renamed_list_shows_on_the_page(self):
        from .models import Shop
        Shop.objects.create(customer_code='C001', name='Old Name')
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('c.csv', (self.HEADER + 'C001,New Name,,,,,,,\n').encode())
        page = self.client.post(reverse('import_shops'), {'csv_file': f})
        self.assertContains(page, 'Renamed (1)')
        self.assertContains(page, 'C001: “Old Name” → “New Name”')

    def test_existing_clients_without_code_get_linked_not_duplicated(self):
        from .models import Shop
        old = Shop.objects.create(name='ELINA STORE', contact_person='Elina')
        Shop.objects.create(name='ELINA STORE')   # an older duplicate stays as it is
        result = self.upload(self.HEADER + 'C050,Elina Store,Retail,,,,,,\n')
        self.assertEqual((result['created'], result['linked']), (0, 1))
        old.refresh_from_db()
        self.assertEqual((old.customer_code, old.customer_type, old.contact_person), ('C050', 'Retail', 'Elina'))
        self.assertEqual(Shop.objects.count(), 2)

    def test_missing_columns_and_rows(self):
        self.assertIn('needs "Customer Code" and "Name"', self.upload('Name,Phone\nX,1\n'))
        result = self.upload(self.HEADER + ',No Code Store,,,,,,,\n\n,,,,,,,,\n')
        self.assertEqual((result['created'], len(result['skipped'])), (0, 1))

    def test_excel_windows_encoding_is_read(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import Shop
        f = SimpleUploadedFile('c.csv', (self.HEADER + 'C9,Fa’atoaga Store,,,,,,,\n').encode('cp1252'))
        self.client.post(reverse('import_shops'), {'csv_file': f})
        self.assertEqual(Shop.objects.get(customer_code='C9').name, 'Fa’atoaga Store')

    def test_monthly_sales_replace_not_add(self):
        from .models import MonthlySales, Shop
        jane = Shop.objects.create(customer_code='C001', name='Jane Store')
        text = ('Customer Code,Customer Name,Month,Sales\n'
                'C001,Jane Store,2026-09,"1,250.50"\n'
                'c001,jane store,Aug-26,$900\n'
                'C001,Jane Store,September 2025,(100.00)\n'
                'C404,Nobody,2026-09,10\n'
                'C001,Old Name For Jane,2026-07,10\n'   # the code decides; the name is only for reading
                'C001,Jane Store,next month,10\n'
                'C001,Jane Store,2026-06,lots\n')
        first = self.upload(text, 'import_monthly_sales')
        self.assertEqual((first['created'], len(first['skipped'])), (4, 3))
        again = self.upload(text.replace('"1,250.50"', '1400'), 'import_monthly_sales')
        self.assertEqual((again['created'], again['updated'], again['unchanged']), (0, 1, 3))
        totals = {f'{r.month:%Y-%m}': str(r.sales) for r in jane.monthly_sales.all()}
        self.assertEqual(totals, {'2026-09': '1400.00', '2026-08': '900.00', '2026-07': '10.00', '2025-09': '-100.00'})
        self.assertEqual(MonthlySales.objects.count(), 4)

    def test_monthly_sales_same_client_twice_in_a_file_adds_up(self):
        from .models import Shop
        jane = Shop.objects.create(customer_code='C001', name='Jane Store')
        text = ('Customer Code,Customer Name,Month,Sales\n'
                'C001,Jane Store,2025-11,"1,000"\n'
                'C001,Jane Store - Branch 2,2025-11,250.50\n'
                'C001,Jane Store,2025-11,(50)\n')
        result = self.upload(text, 'import_monthly_sales')
        self.assertEqual((result['created'], result['combined']), (1, 2))
        self.assertEqual(str(jane.monthly_sales.get().sales), '1200.50')
        again = self.upload(text, 'import_monthly_sales')   # uploading the same file again still replaces, never doubles
        self.assertEqual((again['created'], again['unchanged']), (0, 1))
        self.assertEqual(str(jane.monthly_sales.get().sales), '1200.50')

    def test_rep_keywords_one_per_line(self):
        from .models import SalesRep
        rep = SalesRep(key='fono', name='Fono', streams='Fono\nFaavae', customer_types='Fono\r\nFaavae')
        self.assertEqual((rep.keyword_list(), rep.stream_list()), (['fono', 'faavae'], ['Fono', 'Faavae']))
        self.assertTrue(rep.matches('Faavae Village'))

    def test_sales_pages_and_client_detail(self):
        from .models import MonthlySales, Shop
        jane = Shop.objects.create(customer_code='C001', name='Jane Store', customer_type='Retail', email='j@x.ws')
        MonthlySales.objects.create(shop=jane, month=date(2026, 9, 1), sales='1250.50')
        MonthlySales.objects.create(shop=jane, month=date(2026, 8, 1), sales='900')
        page = self.client.get(reverse('monthly_sales'))
        self.assertEqual((page.context['month'], page.context['total']), ('2026-09', 1250.50))
        csv_text = self.client.get(reverse('monthly_sales'), {'month': 'all', 'export': 1}).content.decode('utf-8-sig')
        self.assertEqual(csv_text.splitlines()[:2], ['Customer Code,Customer Name,Month,Sales', 'C001,Jane Store,2026-09,1250.50'])
        detail = self.client.get(reverse('shop_detail', args=[jane.pk])).content.decode()
        for text in ('C001', 'Retail', 'j@x.ws', 'September 2026', '1,250.50'):
            self.assertIn(text, detail)
        template = self.client.get(reverse('download_shop_template')).content.decode()
        self.assertTrue(template.startswith(self.HEADER.strip()))

    def test_edit_form_keeps_codes_unique(self):
        from .models import Shop
        Shop.objects.create(customer_code='C001', name='Jane Store')
        sam = Shop.objects.create(customer_code='C002', name='Sam Mart', territory='TWN')
        response = self.client.post(reverse('edit_shop', args=[sam.pk]), {'name': 'Sam Mart', 'customer_code': 'c001'})
        self.assertContains(response, 'already used by another client')
        self.client.post(reverse('edit_shop', args=[sam.pk]), {'name': 'Sam Mart', 'customer_code': 'C002',
                                                              'territory': 'twn', 'island': 'Upolu'})
        sam.refresh_from_db()
        self.assertEqual((sam.customer_code, sam.territory), ('C002', 'TWN'))


class CorporateSalesTests(TestCase):
    def setUp(self):
        _manager('office')
        self.client.login(username='office', password='pw')

    def test_customer_types_map_to_managers(self):
        from .corporate import manager_for_type
        cases = {'Ministry of Health': 'ruth', 'MINISTRIES': 'ruth', 'Finance': 'ruth', 'Finance / Banks': 'ruth', 'Banks': 'ruth',
                 'Government / Ministries': 'ruth', 'Laundromats': 'ruth', 'Laundromat': 'ruth',
                 'Tokelau': 'grace', 'Tokelau Clients': 'grace', 'NGO': 'grace', 'NGOs': 'grace', 'Non-Government Org': 'grace',
                 'HORECA': 'judane', 'Hotel': 'judane', 'Café': 'judane', 'Restaurant': 'judane',
                 'Hotels & Resorts': 'judane', 'Restaurants / Cafés / Bakeries': 'judane',
                 'Retail': 'ivan', 'Retail / Supermarkets': 'ivan', 'Supermarket': 'ivan',
                 'Institutions / Organisations': None, 'Corporation': None,
                 'Pharmacies': 'grace', 'Pharmacy': 'grace', 'Mango Traders': None, '': None}
        self.assertEqual({t: manager_for_type(t) for t in cases}, cases)

    def test_page_shows_actual_against_target(self):
        from .models import MonthlySales, SalesTarget, Shop
        from . import corporate
        mof = Shop.objects.create(customer_code='M1', name='Ministry of Finance', customer_type='Ministry')
        laundry = Shop.objects.create(customer_code='L1', name='Clean Laundromat', customer_type='Laundromat')
        hotel = Shop.objects.create(customer_code='H1', name='Beach Hotel', customer_type='Hotel')
        Shop.objects.create(customer_code='R1', name='Corner Store', customer_type='Retail')
        Shop.objects.create(customer_code='C1', name='Big Corp', customer_type='Corporation')
        for shop, amount in ((mof, 6000), (laundry, 2000), (hotel, 5000)):
            MonthlySales.objects.create(shop=shop, month=date(2026, 3, 1), sales=amount)
        MonthlySales.objects.create(shop=mof, month=date(2026, 4, 1), sales=1000)
        SalesTarget.objects.create(manager='ruth', month=date(2026, 3, 1), amount=10000)
        SalesTarget.objects.create(manager='ruth', month=date(2026, 4, 1), amount=10000)

        managers, unmatched = corporate.year_summary(2026, today=date(2026, 4, 15))
        self.assertEqual([m['name'] for m in managers], ['Grace', 'Ruth', 'Judane', 'Ivan'])
        self.assertEqual(managers[3]['client_count'], 1)
        ruth = managers[1]
        self.assertEqual((ruth['client_count'], ruth['actual'][2], ruth['target'][2]), (2, 8000, 10000))
        self.assertEqual((ruth['month_label'], ruth['month_actual'], ruth['month_pct']), ('Apr 2026', 1000, 10))
        self.assertEqual((ruth['ytd_actual'], ruth['ytd_target'], ruth['ytd_pct']), (9000, 20000, 45))
        self.assertEqual([c['shop__name'] for c in ruth['top_clients']], ['Ministry of Finance', 'Clean Laundromat'])
        self.assertEqual((managers[2]['ytd_actual'], managers[2]['ytd_pct'], managers[0]['client_count']), (5000, None, 0))
        self.assertEqual(unmatched, ['Corporation'])

        page = self.client.get(reverse('corporate_sales'), {'year': 2026})
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertLess(html.index('>Grace<'), html.index('>Ruth<'))
        self.assertLess(html.index('>Ruth<'), html.index('>Judane<'))
        self.assertIn('Ministries', html)

    def test_all_slide_combines_every_stream(self):
        from .models import MonthlySales, SalesTarget, Shop
        from . import corporate
        mof = Shop.objects.create(customer_code='M1', name='Ministry of Finance', customer_type='Ministry')
        hotel = Shop.objects.create(customer_code='H1', name='Beach Hotel', customer_type='Hotel')
        MonthlySales.objects.create(shop=mof, month=date(2026, 3, 1), sales=12000)
        MonthlySales.objects.create(shop=hotel, month=date(2026, 3, 1), sales=5000)
        SalesTarget.objects.create(manager='ruth', month=date(2026, 3, 1), amount=10000)

        overall = corporate.combined_summary(corporate.year_summary(2026, today=date(2026, 3, 15))[0])
        self.assertEqual((overall['actual'][2], overall['target'][2], overall['target'][1]), (17000, 10000, None))
        ytd = {r['key']: r for r in overall['tables'][0]['rows']}
        self.assertEqual((ytd['ruth']['variance'], ytd['ruth']['variance_pct']), (2000, 20.0))
        self.assertEqual((ytd['judane']['actual'], ytd['judane']['variance']), (5000, None))   # no target: no variance
        self.assertNotIn('grace', ytd)   # no sales: left off the table
        total = overall['tables'][0]['total']
        self.assertEqual((total['actual'], total['target'], total['variance'], total['variance_pct']), (17000, 10000, 2000, 20.0))

        html = self.client.get(reverse('corporate_sales'), {'year': 2026}).content.decode()
        self.assertIn('id="slide-all"', html)
        self.assertIn('Variance %', html)
        self.assertIn('id="sum-png"', html)

    def test_graph_compares_with_last_year(self):
        import json as _json
        from .models import MonthlySales, Shop
        from . import corporate
        hotel = Shop.objects.create(customer_code='H1', name='Beach Hotel', customer_type='HORECA')
        MonthlySales.objects.create(shop=hotel, month=date(2025, 11, 1), sales='2442955.86')
        MonthlySales.objects.create(shop=hotel, month=date(2026, 3, 1), sales=5000)
        judane = next(m for m in corporate.year_summary(2026, today=date(2026, 4, 1))[0] if m['key'] == 'judane')
        self.assertEqual((judane['previous'][10], judane['previous'][2], judane['actual'][2]), (Decimal('2442955.86'), None, 5000))
        data = _json.loads(self.client.get(reverse('corporate_sales'), {'year': 2026}).context['chart_data'])
        self.assertEqual(next(m for m in data['managers'] if m['key'] == 'judane')['previous'][10], 2442955.86)
        self.assertEqual(data['all']['previous'][10], 2442955.86)

    def test_targets_form_saves_clears_and_rejects_bad_input(self):
        from .models import SalesTarget
        url = reverse('corporate_targets') + '?year=2026'
        self.client.post(url, {'grace_1': '10,000', 'grace_2': '$12000', 'judane_12': '5000'})
        self.assertEqual({(t.manager, t.month.month): int(t.amount) for t in SalesTarget.objects.all()},
                         {('grace', 1): 10000, ('grace', 2): 12000, ('judane', 12): 5000})
        self.client.post(url, {'grace_1': '11000'})   # blank boxes remove targets
        self.assertEqual(list(SalesTarget.objects.values_list('manager', 'amount')), [('grace', 11000)])
        response = self.client.post(url, {'grace_1': '9000', 'ruth_3': 'lots'})
        self.assertContains(response, 'Nothing was saved')
        self.assertEqual(SalesTarget.objects.get().amount, 11000)


class CorporateManagerPageTests(TestCase):
    def setUp(self):
        from .models import MonthlySales, Shop
        _manager('office')
        self.client.login(username='office', password='pw')
        self.mof = Shop.objects.create(customer_code='M1', name='Ministry of Finance', customer_type='Government / Ministries',
                                       territory='TWN', contact_person='Losa')
        self.laundry = Shop.objects.create(customer_code='L1', name='Clean Laundromat', customer_type='Laundromats', territory='EC1')
        self.quiet = Shop.objects.create(customer_code='L2', name='Quiet Laundromat', customer_type='Laundromats')
        Shop.objects.create(customer_code='H1', name='Beach Hotel', customer_type='Hotels & Resorts')
        MonthlySales.objects.create(shop=self.mof, month=date(2026, 3, 1), sales=6000)
        MonthlySales.objects.create(shop=self.mof, month=date(2026, 4, 1), sales=1000)
        MonthlySales.objects.create(shop=self.laundry, month=date(2026, 3, 1), sales=2000)

    def get(self, **params):
        return self.client.get(reverse('corporate_manager', args=['ruth']), {'year': 2026, **params})

    def names(self, response):
        return [getattr(r, 'name', None) or r.shop.name for r in response.context['page_obj']]

    def test_total_shows_cents_not_rounded(self):
        from .models import MonthlySales
        MonthlySales.objects.create(shop=self.quiet, month=date(2025, 11, 1), sales='2442955.86')
        r = self.client.get(reverse('corporate_manager', args=['ruth']), {'year': 2025, 'month': 11})
        self.assertContains(r, '2,442,955.86')
        self.assertNotContains(r, '2,442,956<')

    def test_clients_sorted_by_sales_with_filters_and_search(self):
        r = self.get()
        self.assertEqual(self.names(r), ['Ministry of Finance', 'Clean Laundromat', 'Quiet Laundromat'])
        self.assertEqual((r.context['total'], r.context['client_total'], r.context['with_sales']), (9000, 3, 2))
        self.assertEqual(self.names(self.get(month=3, sales='with')), ['Ministry of Finance', 'Clean Laundromat'])
        self.assertEqual(self.names(self.get(sales='without')), ['Quiet Laundromat'])
        self.assertEqual(self.names(self.get(type='Laundromats', sort='name')), ['Clean Laundromat', 'Quiet Laundromat'])
        self.assertEqual(self.names(self.get(territory='TWN')), ['Ministry of Finance'])
        self.assertEqual(self.names(self.get(q='losa')), ['Ministry of Finance'])
        self.assertEqual(self.names(self.get(q='l1')), ['Clean Laundromat'])
        self.assertEqual(self.get(month=4).context['total'], 1000)

    def test_each_sale_view_and_export(self):
        r = self.get(view='sales')
        self.assertEqual([(x.shop.name, x.month.month) for x in r.context['page_obj']],
                         [('Ministry of Finance', 4), ('Ministry of Finance', 3), ('Clean Laundromat', 3)])
        self.assertNotIn('view=sales&amp;view', r.content.decode())   # links don't pile up parameters
        csv_text = self.get(view='sales', export=1).content.decode('utf-8-sig').splitlines()
        self.assertEqual(csv_text[0], 'Customer Code,Customer Name,Customer Type,Looked After By,Month,Sales')
        self.assertEqual(len(csv_text), 4)
        clients_csv = self.get(export=1).content.decode('utf-8-sig').splitlines()
        self.assertTrue(clients_csv[1].startswith('M1,Ministry of Finance,Government / Ministries,Ruth,Losa'))

    def test_cards_link_to_pages_and_unknown_manager_404(self):
        page = self.client.get(reverse('corporate_sales'), {'year': 2026}).content.decode()
        for key in ('grace', 'ruth', 'judane'):
            self.assertIn(reverse('corporate_manager', args=[key]), page)
        self.assertEqual(self.client.get(reverse('corporate_manager', args=['nobody'])).status_code, 404)

    def test_all_clients_customer_type_filter(self):
        from .models import Shop
        Shop.objects.create(name='No Type Store')
        r = self.client.get(reverse('shop_list'), {'customer_type': 'Laundromats'})
        self.assertEqual({s.name for s in r.context['page_obj']}, {'Clean Laundromat', 'Quiet Laundromat'})
        self.assertContains(r, 'Laundromats (2)')
        r = self.client.get(reverse('shop_list'), {'customer_type': '__none__'})
        self.assertEqual([s.name for s in r.context['page_obj']], ['No Type Store'])


class YearToDateTargetTests(TestCase):
    def test_ytd_only_compares_months_that_have_targets(self):
        from .models import MonthlySales, SalesTarget, Shop
        from . import corporate
        hotel = Shop.objects.create(customer_code='H1', name='Beach Hotel', customer_type='HORECA')
        for month, amount in ((1, 3000), (2, 3000), (3, 2000)):
            MonthlySales.objects.create(shop=hotel, month=date(2026, month, 1), sales=amount)
        SalesTarget.objects.create(manager='judane', month=date(2026, 3, 1), amount=4000)   # only March has a target

        judane = corporate.year_summary(2026, today=date(2026, 3, 20))[0][2]
        self.assertEqual((judane['ytd_actual'], judane['ytd_actual_on_target'], judane['ytd_target'], judane['ytd_pct']),
                         (8000, 2000, 4000, 50))   # March 2,000 vs 4,000, not Jan–Mar 8,000 vs 4,000 (200%)
        self.assertEqual((judane['ytd_target_months'], judane['ytd_missing_months']), ('Mar', 'Jan–Feb'))

        SalesTarget.objects.create(manager='judane', month=date(2026, 1, 1), amount=3000)
        SalesTarget.objects.create(manager='judane', month=date(2026, 2, 1), amount=3000)
        judane = corporate.year_summary(2026, today=date(2026, 3, 20))[0][2]
        self.assertEqual((judane['ytd_actual_on_target'], judane['ytd_target'], judane['ytd_pct'], judane['ytd_missing_months']),
                         (8000, 10000, 80, ''))

    def test_month_span(self):
        from .corporate import month_span
        self.assertEqual(month_span([0, 1, 2, 5, 7, 8]), 'Jan–Mar, Jun, Aug–Sep')
        self.assertEqual(month_span([]), '')


class CombinedCorporateClientsTests(TestCase):
    # same clients and helpers as the per-person page tests, without re-running those tests
    setUp = CorporateManagerPageTests.setUp
    names = CorporateManagerPageTests.names

    def test_all_corporate_clients_together_with_owner(self):
        url = reverse('corporate_manager', args=['all'])
        r = self.client.get(url, {'year': 2026, 'sort': 'name'})
        self.assertEqual(self.names(r), ['Beach Hotel', 'Clean Laundromat', 'Ministry of Finance', 'Quiet Laundromat'])
        self.assertEqual({c.name: c.owner['name'] for c in r.context['page_obj']},
                         {'Beach Hotel': 'Judane', 'Clean Laundromat': 'Ruth', 'Ministry of Finance': 'Ruth',
                          'Quiet Laundromat': 'Ruth'})
        self.assertContains(r, 'Corporate Sales Clients')
        self.assertContains(r, 'Looked After By')
        judane_only = self.client.get(url, {'year': 2026, 'person': 'judane'})
        self.assertEqual(self.names(judane_only), ['Beach Hotel'])
        csv_rows = self.client.get(url, {'year': 2026, 'view': 'sales', 'export': 1}).content.decode('utf-8-sig').splitlines()
        self.assertEqual(csv_rows[0], 'Customer Code,Customer Name,Customer Type,Looked After By,Month,Sales')
        self.assertIn(',Ruth,', csv_rows[1])

    def test_corporate_page_button_opens_combined_list(self):
        page = self.client.get(reverse('corporate_sales')).content.decode()
        self.assertIn('Corporate Sales Clients', page)
        self.assertNotIn('HORECA Client List', page)
        self.assertIn(reverse('corporate_manager', args=['all']), page)


class YearToDateTotalTests(TestCase):
    def test_card_shows_total_of_all_months(self):
        from .models import MonthlySales, SalesTarget, Shop
        _manager('office')
        self.client.login(username='office', password='pw')
        hotel = Shop.objects.create(customer_code='H1', name='Beach Hotel', customer_type='HORECA')
        this_year = date.today().year
        for month in range(1, date.today().month + 1):
            MonthlySales.objects.create(shop=hotel, month=date(this_year, month, 1), sales=1000)
        SalesTarget.objects.create(manager='judane', month=date(this_year, date.today().month, 1), amount=4000)
        page = self.client.get(reverse('corporate_sales')).content.decode()
        total = f'{1000 * date.today().month:,}.00'
        self.assertIn(f'<div class="cs-big">{total}</div>', page)   # the big Year to date figure is every month combined
        self.assertIn('1,000.00 of 4,000.00', page)    # the target line only covers the month with a target


class ReportsTests(TestCase):
    def setUp(self):
        from .models import MonthlySales, SalesTarget, Shop
        _manager('office')
        self.client.login(username='office', password='pw')
        mof = Shop.objects.create(customer_code='M1', name='Ministry of Finance', customer_type='Government / Ministries', territory='TWN')
        hotel = Shop.objects.create(customer_code='H1', name='Beach Hotel', customer_type='HORECA', island='Savaii')
        Shop.objects.create(customer_code='R1', name='Corner Store', customer_type='Retail / Supermarkets')
        for shop, month, amount in ((mof, 1, 100), (mof, 2, 300), (hotel, 2, 500)):
            MonthlySales.objects.create(shop=shop, month=date(2026, month, 1), sales=amount)
        SalesTarget.objects.create(manager='ruth', month=date(2026, 2, 1), amount=400)

    def download(self, **params):
        response = self.client.get(reverse('download_report'), params)
        return list(csv.reader(response.content.decode('utf-8-sig').splitlines()))

    def test_reports_need_login(self):
        self.client.logout()
        for url in (reverse('reports'), reverse('download_report') + '?type=shops'):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_page_lists_new_reports(self):
        page = self.client.get(reverse('reports')).content.decode()
        for text in ('All Clients', 'Monthly Sales', 'Corporate Sales vs Target', 'FE Order Sales', 'Product Catalogue',
                     'Promotions', 'Sponsorships', 'Government / Ministries'):
            self.assertIn(text, page)

    def test_clients_report_filters(self):
        rows = self.download(type='shops', customer_type='HORECA')
        self.assertEqual(rows[0][:3], ['Customer Code', 'Name', 'Customer Type'])
        self.assertEqual([r[1] for r in rows[1:]], ['Beach Hotel'])
        self.assertEqual([r[1] for r in self.download(type='shops', territory='TWN')[1:]], ['Ministry of Finance'])

    def test_monthly_sales_layouts(self):
        rows = self.download(type='monthly_sales', year=2026)
        self.assertEqual(rows[0], ['Customer Code', 'Customer Name', 'Customer Type', 'Corporate Manager', 'Month', 'Sales'])
        self.assertEqual(len(rows), 4)
        clients = self.download(type='monthly_sales', year=2026, layout='clients')
        self.assertEqual([(r[1], r[3], r[5]) for r in clients[1:]], [('Beach Hotel', 'Judane', '500.00'), ('Ministry of Finance', 'Ruth', '400.00')])
        pivot = self.download(type='monthly_sales', year=2026, layout='pivot', person='ruth')
        self.assertEqual(pivot[0][4:6] + pivot[0][-1:], ['Jan 2026', 'Feb 2026', 'Total'])
        self.assertEqual(pivot[1][:2] + pivot[1][4:6] + pivot[1][-1:], ['M1', 'Ministry of Finance', '100.00', '300.00', '400.00'])
        self.assertEqual(len(pivot), 2)
        feb = self.download(type='monthly_sales', year=2026, month=2, person='corporate')
        self.assertEqual(len(feb), 3)

    def test_corporate_report(self):
        rows = self.download(type='corporate', year=2026, person='ruth')
        self.assertEqual(rows[0], ['Manager', 'Streams', 'Month', 'Actual Sales', 'Target', 'Variance', '% of Target'])
        feb = rows[2]
        self.assertEqual(feb[2:], ['Feb 2026', '300.00', '400.00', '-100.00', '75%'])
        self.assertEqual(rows[-1][:5], ['Ruth', 'TOTAL', '2026', '400.00', '400.00'])
        self.assertEqual(len(rows), 14)   # header + 12 months + total

    def test_horeca_business_type_filter_no_longer_breaks_report(self):
        from .models import Business
        Business.objects.create(name='Sunset Cafe', business_type='CAFE')
        Business.objects.create(name='Big Hotel', business_type='HOTEL')
        response = self.client.get(reverse('download_report'), {'type': 'horecca', 'business_type': 'CAFE'})
        self.assertIn('horecca_report', response['Content-Disposition'])
        self.assertEqual([r[1] for r in csv.reader(response.content.decode().splitlines())][1:], ['Sunset Cafe'])


class CorporateSliderTests(TestCase):
    def test_one_slide_per_person_with_navigation(self):
        _manager('office')
        self.client.login(username='office', password='pw')
        html = self.client.get(reverse('corporate_sales')).content.decode()
        self.assertEqual(html.count('class="cs-slide"'), 5)   # All streams, then one per person
        self.assertEqual(html.count('role="tab"'), 5)
        self.assertLess(html.index('id="slide-all"'), html.index('id="slide-grace"'))
        for text in ('cs-prev', 'cs-next', 'id="slide-grace"', 'id="slide-ivan"', '"currentMonth"', '"name": "Ruth"'):
            self.assertIn(text, html)
        self.assertLess(html.index('id="slide-grace"'), html.index('id="slide-ruth"'))
        self.assertLess(html.index('id="slide-judane"'), html.index('id="slide-ivan"'))


class ProductSalesTests(TestCase):
    HEADER = 'Product Code,Product Name,Date (YY-MM),Total Sales\n'

    def setUp(self):
        _manager('office')
        self.client.login(username='office', password='pw')

    def upload(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('p.csv', text.encode('utf-8-sig'), content_type='text/csv')
        r = self.client.post(reverse('import_product_sales'), {'csv_file': f})
        return r.context.get('result') or r.context.get('error')

    def seed(self):
        return self.upload(self.HEADER +
                           'TT1,Tip Top Vanilla 2L,25-01,100\nTT1,Tip Top Vanilla 2L,25-02,200\nTT1,Tip Top Vanilla 2L,25-03,300\n'
                           'TT1,Tip Top Vanilla 2L,26-01,150\nTT1,Tip Top Vanilla 2L,26-02,250\n'
                           'CK1,Coke 1.5L,26-01,"1,000"\nCK1,Coke 1.5L,26-02,500\n')

    def test_upload_parses_yy_mm_and_is_safe_to_repeat(self):
        from .models import ProductSales
        first = self.seed()
        self.assertEqual((first['created'], first['skipped']), (7, []))
        self.assertEqual(ProductSales.objects.get(product_code='TT1', month=date(2026, 2, 1)).total_sales, 250)
        again = self.seed()
        self.assertEqual((again['created'], again['updated'], again['unchanged']), (0, 0, 7))
        changed = self.upload(self.HEADER + 'TT1,Tip Top Vanilla 2 Litre,26-02,275\n,No Code,26-01,5\nCK1,Coke,next month,5\nCK1,Coke,26-03,lots\n')
        self.assertEqual((changed['updated'], len(changed['skipped'])), (1, 3))
        row = ProductSales.objects.get(product_code='TT1', month=date(2026, 2, 1))
        self.assertEqual((row.total_sales, row.product_name), (275, 'Tip Top Vanilla 2 Litre'))
        self.assertIn('needs these columns', self.upload('Code,Name\nA,B\n'))

    def test_parse_yy_mm(self):
        from .product_sales import parse_yy_mm
        for text in ('26-09', '26/9', '2026-09', 'Sep-26', 'September 2026'):
            self.assertEqual(parse_yy_mm(text), date(2026, 9, 1), text)
        with self.assertRaises(ValueError):
            parse_yy_mm('26-13')

    def test_charts_follow_filters(self):
        from . import product_sales
        self.seed()
        a = product_sales.analytics(product_sales.read_filters({}))
        self.assertEqual((a['yoy']['year'], a['yoy']['compare']), (2026, 2025))
        self.assertEqual(a['yoy']['this'][:3], [1150, 750, None])
        self.assertEqual(a['yoy']['last'][:3], [100, 200, 300])
        self.assertEqual(a['cumulative']['this'][:3], [1150, 1900, None])
        k = a['kpi']
        self.assertEqual((k['ytd'], k['ytd_before'], k['growth'], k['through'], k['best_month'], k['products']),
                         (1900, 300, 533.3, 'Feb', 'Jan 2026', 2))   # Jan–Feb both years, not all of 2025
        self.assertEqual([r['product_code'] for r in a['top']['rows']], ['CK1', 'TT1'])
        self.assertEqual(len(a['trend']['labels']), 5)

        tt = product_sales.analytics(product_sales.read_filters({'product': 'tt1'}))
        self.assertEqual(tt['yoy']['this'][:2], [150, 250])
        ranged = product_sales.analytics(product_sales.read_filters({'from': '2026-01', 'to': '2026-01'}))
        self.assertEqual((ranged['trend']['labels'], ranged['top']['label']), (['Jan 26'], 'selected months'))
        searched = product_sales.table(product_sales.read_filters({'q': 'coke'}))
        self.assertEqual({r.product_code for r in searched}, {'CK1'})

    def test_page_pins_and_quick_links(self):
        self.seed()
        page = self.client.get(reverse('product_sales'))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['row_count'], 7)
        self.assertContains(page, 'to pin it here')
        self.client.post(reverse('product_sales_pin'), {'code': 'TT1', 'next': reverse('product_sales')})
        links = self.client.get(reverse('product_sales'), {'lm': 2}).context['links']   # Jan–Feb 2026 vs Jan–Feb 2025
        self.assertEqual([(l['code'], l['total'], l['growth']) for l in links], [('TT1', 400, 33.3)])
        selected = self.client.get(reverse('product_sales'), {'product': 'TT1'})
        self.assertEqual((selected.context['selected_name'], selected.context['row_count']), ('Tip Top Vanilla 2L', 5))
        self.client.post(reverse('product_sales_pin'), {'code': 'TT1'})   # second click unpins
        self.assertEqual(self.client.get(reverse('product_sales')).context['links'], [])
        self.client.post(reverse('product_sales_pin'), {'code': 'NOPE'})   # unknown codes can't be pinned
        self.assertEqual(self.client.get(reverse('product_sales')).context['links'], [])

    def test_excel_report_and_csv(self):
        from io import BytesIO
        from openpyxl import load_workbook
        self.seed()
        r = self.client.get(reverse('product_sales_export'), {'q': 'tip'})
        self.assertIn('.xlsx', r['Content-Disposition'])
        wb = load_workbook(BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ['Summary', 'Monthly Trend', '2026 vs 2025', 'Year to Date', 'Top Products', 'Data'])
        self.assertEqual(len(wb['2026 vs 2025']._charts), 1)
        self.assertEqual([c.value for c in wb['Data'][1]], ['Product Code', 'Product Name', 'Date (YY-MM)', 'Total Sales'])
        self.assertEqual(wb['Data'].max_row, 6)   # header + Tip Top's 5 months
        self.assertIn('search "tip"', wb['Summary']['B3'].value)
        one = load_workbook(BytesIO(self.client.get(reverse('product_sales_export'), {'sheet': 'top'}).content))
        self.assertEqual(one.sheetnames, ['Top Products'])
        csv_rows = self.client.get(reverse('product_sales_export'), {'format': 'csv', 'product': 'CK1'}).content.decode('utf-8-sig').splitlines()
        self.assertEqual(csv_rows, ['Product Code,Product Name,Date (YY-MM),Total Sales', 'CK1,Coke 1.5L,26-02,500.00', 'CK1,Coke 1.5L,26-01,1000.00'])

    def test_empty_page_invites_upload(self):
        self.assertContains(self.client.get(reverse('product_sales')), 'No product sales yet')


class ProductGroupTests(TestCase):
    def setUp(self):
        from .models import ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        for code, name, amount in (('TT1', 'Tip Top Vanilla 2L', 100), ('TT2', 'TIP TOP Cookies & Cream', 200),
                                   ('TT3', 'Tiptop Banana Split 16L', 300), ('CK1', 'Coke 1.5L', 1000), ('IC9', 'Kiwi Ice Block', 50)):
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 9, 1), total_sales=amount)

    def test_keywords_and_extra_codes(self):
        from .models import ProductGroup, ProductSales
        g = ProductGroup.objects.create(name='Tip Top', keywords='tip top, tiptop', product_codes='IC9\n')
        self.assertEqual(set(ProductSales.objects.filter(g.match()).values_list('product_code', flat=True)),
                         {'TT1', 'TT2', 'TT3', 'IC9'})
        ProductSales.objects.create(product_code='TT4', product_name='Tip Top Mango 1L', month=date(2026, 9, 1), total_sales=5)
        self.assertIn('TT4', ProductSales.objects.filter(g.match()).values_list('product_code', flat=True))   # new products join
        self.assertFalse(ProductSales.objects.filter(ProductGroup(name='Empty').match()).exists())

    def test_create_preview_validate_edit_delete(self):
        from .models import ProductGroup
        url = reverse('product_group_add')
        prefilled = self.client.get(url, {'name': 'Tip Top', 'keywords': 'tip top'})
        self.assertEqual(prefilled.context['member_count'], 2)   # "Tiptop" needs its own keyword
        preview = self.client.post(url, {'name': 'Tip Top', 'keywords': 'tip top,tiptop', 'preview': '1'})
        self.assertEqual((preview.context['member_count'], ProductGroup.objects.count()), (3, 0))
        self.assertEqual(self.client.post(url, {'name': '', 'keywords': ''}).context['errors'],
                         ['Give the group a name, e.g. Tip Top.', 'Add at least one keyword or product code.'])
        saved = self.client.post(url, {'name': 'Tip Top', 'keywords': ' tip top ,, tiptop ', 'product_codes': 'IC9, NOPE'})
        g = ProductGroup.objects.get()
        self.assertRedirects(saved, reverse('product_sales') + f'?group={g.pk}', fetch_redirect_response=False)
        self.assertEqual((g.keywords, g.code_list()), ('tip top, tiptop', ['IC9', 'NOPE']))
        edit = self.client.get(reverse('product_group_edit', args=[g.pk]))
        self.assertEqual((edit.context['member_count'], edit.context['unknown_codes']), (4, ['NOPE']))
        self.assertIn('already a group', self.client.post(url, {'name': 'tip top', 'keywords': 'x'}).context['errors'][0])
        self.client.post(reverse('product_group_edit', args=[g.pk]), {'delete': '1'})
        self.assertFalse(ProductGroup.objects.exists())

    def test_page_and_export_follow_the_group(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from .models import ProductGroup
        g = ProductGroup.objects.create(name='Tip Top', keywords='tip top, tiptop')
        page = self.client.get(reverse('product_sales'), {'group': g.pk})
        self.assertEqual(page.context['row_count'], 3)
        self.assertEqual([(x['name'], x['products'], x['total']) for x in page.context['groups']], [('Tip Top', 3, 600)])
        self.assertEqual(page.context['kpi']['ytd'], 600)
        self.assertContains(page, '🗂 Tip Top')
        within = self.client.get(reverse('product_sales'), {'group': g.pk, 'q': 'cookies'})
        self.assertEqual(within.context['row_count'], 1)   # search inside the group
        wb = load_workbook(BytesIO(self.client.get(reverse('product_sales_export'), {'group': g.pk}).content))
        self.assertIn('group Tip Top', wb['Summary']['B3'].value)
        self.assertEqual(wb['Data'].max_row, 4)

    def test_search_offers_to_save_as_group(self):
        page = self.client.get(reverse('product_sales'), {'q': 'tip top'})
        self.assertContains(page, 'Save search as group')
        self.assertContains(page, reverse('product_group_add') + '?name=Tip%20Top&keywords=tip%20top')


class ProductTargetColourTests(TestCase):
    def setUp(self):
        from .models import PinnedProduct, ProductGroup, ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        # Sep 2025 is each product's target for Sep 2026 (the latest month uploaded)
        for code, name, last_sep, this_sep in (('G1', 'Green Tea', 1000, 1200),     # 120% → green
                                               ('O1', 'Orange Juice', 1000, 950),   # 95%  → orange
                                               ('R1', 'Red Wine', 1000, 500),       # 50%  → red
                                               ('N1', 'New Snack', None, 300)):     # no target
            if last_sep is not None:
                ProductSales.objects.create(product_code=code, product_name=name, month=date(2025, 9, 1), total_sales=last_sep)
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 8, 1), total_sales=9999)
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 9, 1), total_sales=this_sep)
            PinnedProduct.objects.create(product_code=code)
        ProductGroup.objects.create(name='Drinks', keywords='tea, juice, wine')

    def test_thresholds(self):
        from .product_sales import target_status
        self.assertEqual(target_status(100, 100), (100, 'good'))
        self.assertEqual(target_status(99, 100), (99, 'close'))
        self.assertEqual(target_status(70, 100), (70, 'close'))
        self.assertEqual(target_status(69.4, 100), (69, 'behind'))
        self.assertEqual(target_status(None, 100), (0, 'behind'))   # no sales this month yet
        self.assertEqual(target_status(50, None), (None, 'none'))

    def test_first_card_is_current_month_only(self):
        page = self.client.get(reverse('product_sales'))
        k = page.context['kpi']
        self.assertEqual((k['month_label'], k['month_value'], k['month_before'], k['month_pct']), ('Sep 2026', 2950, 3000, 98))
        self.assertContains(page, 'Sales · Sep 2026')

    def test_quick_link_colours(self):
        page = self.client.get(reverse('product_sales'), {'lm': 9})
        self.assertEqual({l['code']: (l['month_sales'], l['target'], l['pct'], l['status']) for l in page.context['links']},
                         {'G1': (1200, 1000, 120, 'good'), 'O1': (950, 1000, 95, 'close'),
                          'R1': (500, 1000, 50, 'behind'), 'N1': (300, None, None, 'none')})
        drinks = page.context['groups'][0]
        self.assertEqual((drinks['month_sales'], drinks['target'], drinks['pct'], drinks['status']), (2650, 3000, 88, 'close'))
        html = page.content.decode()
        for cls in ('ps-link s-good', 'ps-link s-close', 'ps-link s-behind', 'of 1k', '70–99%', 'Below 70%'):
            self.assertIn(cls, html)
        self.assertEqual(page.context['target_month'], 'Sep 2025')


class QuickLinksPanelTests(TestCase):
    def setUp(self):
        from .models import PinnedProduct, ProductGroup, ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        for code, name in (('TT1', 'Tip Top Vanilla 2L'), ('CK1', 'Coke 1.5L')):
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2025, 9, 1), total_sales=3025562)
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 9, 1), total_sales=3000000)
        PinnedProduct.objects.create(product_code='CK1')
        self.tiptop = ProductGroup.objects.create(name='Tip Top Ice Cream', keywords='tip top')
        ProductGroup.objects.create(name='Soft Drinks', keywords='coke')

    def test_search_also_finds_groups(self):
        page = self.client.get(reverse('product_sales'), {'q': 'tip'})
        self.assertEqual([g['name'] for g in page.context['matching_groups']], ['Tip Top Ice Cream'])
        self.assertContains(page, 'Groups matching “tip”')
        self.assertContains(page, f'group={self.tiptop.pk}')
        self.assertEqual(page.context['row_count'], 2)   # the product table still shows the matching products
        self.assertEqual(self.client.get(reverse('product_sales'), {'q': 'zzz'}).context['matching_groups'], [])
        inside = self.client.get(reverse('product_sales'), {'q': 'tip', 'group': self.tiptop.pk})
        self.assertEqual(inside.context['matching_groups'], [])   # already in a group: no need to offer it

    def test_compact_scrollable_panel(self):
        html = self.client.get(reverse('product_sales'), {'lm': 9}).content.decode()
        for text in ('ps-links-list', 'id="ps-find"', 'of 3.0M', 'Lowest first · 3', '＋ New group'):
            self.assertIn(text, html)
        self.assertNotIn('data-spark', html)

    def test_short_money(self):
        from .product_sales import short_money
        self.assertEqual([short_money(v) for v in (3025562, 125076, 1600, 1000, 950, None)],
                         ['3.0M', '125k', '1.6k', '1k', '950', ''])


class ManualGroupPickTests(TestCase):
    def setUp(self):
        from .models import ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        for code, name, amount in (('TT1', 'Tip Top Vanilla 2L', 100), ('TT2', 'Tip Top Cookies', 200),
                                   ('CK1', 'Coke 1.5L', 1000), ('RC1', 'Rice 25kg', 50)):
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 9, 1), total_sales=amount)

    def codes(self, group):
        from .models import ProductSales
        return set(ProductSales.objects.filter(group.match()).values_list('product_code', flat=True))

    def test_hand_picked_group_without_keywords(self):
        from .models import ProductGroup
        r = self.client.post(reverse('product_group_add'), {'name': 'My Mix', 'keywords': '',
                                                            'product_codes': 'CK1\nRC1\nCK1', 'exclude_codes': ''})
        g = ProductGroup.objects.get()
        self.assertEqual((g.code_list(), self.codes(g)), (['CK1', 'RC1'], {'CK1', 'RC1'}))
        page = self.client.get(reverse('product_sales'), {'group': g.pk})
        self.assertEqual((page.context['row_count'], page.context['kpi']['month_value']), (2, 1050))

    def test_take_out_a_keyword_match_and_add_any_product(self):
        from .models import ProductGroup
        self.client.post(reverse('product_group_add'), {'name': 'Tip Top', 'keywords': 'tip top',
                                                        'product_codes': 'RC1', 'exclude_codes': 'TT2'})
        g = ProductGroup.objects.get()
        self.assertEqual((self.codes(g), g.exclude_list()), ({'TT1', 'RC1'}, ['TT2']))
        form = self.client.get(reverse('product_group_edit', args=[g.pk]))
        self.assertEqual((form.context['picked'], form.context['excluded']), (['RC1'], ['TT2']))
        self.assertEqual(len(form.context['catalogue']), 4)
        self.assertEqual(form.context['catalogue'][0][:2], ['CK1', 'Coke 1.5L'])   # biggest seller first
        self.assertContains(form, 'id="pg-catalogue"')


class QuickLinkTargetTests(TestCase):
    def setUp(self):
        from .models import PinnedProduct, ProductGroup, ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        for code, name in (('TT1', 'Tip Top Vanilla'), ('CK1', 'Coke 1.5L')):
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2025, 9, 1), total_sales=1000)
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 9, 1), total_sales=800)
        PinnedProduct.objects.create(product_code='CK1')
        self.group = ProductGroup.objects.create(name='Tip Top', keywords='tip top')
        self.url = reverse('quick_link_targets') + '?year=2026'

    def links(self):
        page = self.client.get(reverse('product_sales'), {'lm': 9})
        return page.context['groups'][0], page.context['links'][0], page

    def test_blank_uses_last_year_and_manual_overrides(self):
        g, p, _ = self.links()
        self.assertEqual((g['target'], g['pct'], g['status'], g['manual_target']), (1000, 80, 'close', False))
        self.client.post(self.url, {f'g{self.group.pk}_9': '1,600', 'pCK1_9': '$700'})
        g, p, page = self.links()
        self.assertEqual((g['target'], g['pct'], g['status'], g['manual_target']), (1600, 50, 'behind', True))
        self.assertEqual((p['target'], p['pct'], p['status'], p['manual_target']), (700, 114, 'good', True))
        self.assertContains(page, 'of 🎯1.6k')
        self.assertContains(page, 'Quick-link targets for 2026 saved.')
        self.client.post(self.url, {f'g{self.group.pk}_9': '', 'pCK1_9': '700'})   # blank = back to last year
        g, p, _ = self.links()
        self.assertEqual((g['target'], g['manual_target'], p['target']), (1000, False, 700))

    def test_grid_shows_last_year_and_rejects_bad_numbers(self):
        from .models import QuickLinkTarget
        grid = self.client.get(self.url)
        rows = grid.context['rows']
        self.assertEqual([(r['kind'], r['label']) for r in rows], [('group', 'Tip Top'), ('product', 'Coke 1.5L')])
        self.assertEqual((rows[0]['cells'][8]['auto'], rows[0]['cells'][0]['auto']), (1000, None))
        bad = self.client.post(self.url, {f'g{self.group.pk}_1': '500', 'pCK1_2': 'lots'})
        self.assertContains(bad, 'Nothing was saved')
        self.assertContains(bad, 'value="lots"')
        self.assertFalse(QuickLinkTarget.objects.exists())

    def test_deleting_a_group_removes_its_targets(self):
        from .models import QuickLinkTarget
        self.client.post(self.url, {f'g{self.group.pk}_9': '1600'})
        self.group.delete()
        self.assertFalse(QuickLinkTarget.objects.exists())


class ProductTableSearchTests(TestCase):
    def setUp(self):
        from .models import ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        for code, name in (('TT1', 'Tip Top Vanilla'), ('TT2', 'Tip Top Cookies'), ('CK1', 'Coke 1.5L')):
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 9, 1), total_sales=100)

    def test_table_search_leaves_charts_alone(self):
        page = self.client.get(reverse('product_sales'), {'tq': 'cookies'})
        self.assertEqual((page.context['row_count'], page.context['table_total']), (1, 3))
        self.assertEqual(page.context['kpi']['month_value'], 300)   # figures and charts still cover everything
        self.assertContains(page, '1 of 3 rows')
        self.assertContains(page, 'id="ps-tq" value="cookies"')

    def test_combines_with_other_filters_and_exports(self):
        page = self.client.get(reverse('product_sales'), {'q': 'tip top', 'tq': 'tt2', 'sort': 'name'})
        self.assertEqual([r.product_code for r in page.context['page_obj']], ['TT2'])
        self.assertEqual(page.context['kpi']['month_value'], 200)   # the top search still applies to the charts
        self.assertIn(('q', 'tip top'), page.context['table_keep'])
        self.assertNotIn('tq=', page.context['clear_table_query'])
        rows = self.client.get(reverse('product_sales_export'), {'tq': 'coke', 'format': 'csv'}).content.decode('utf-8-sig').splitlines()
        self.assertEqual(rows[1:], ['CK1,Coke 1.5L,26-09,100.00'])
        self.assertContains(self.client.get(reverse('product_sales'), {'tq': 'zzz'}), 'No products in the table match “zzz”')


class LiveTableSearchTests(TestCase):
    def setUp(self):
        from .models import ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        for code, name in (('TT1', 'Tip Top Vanilla'), ('TT2', 'Tip Top Cookies'), ('CK1', 'Coke 1.5L')):
            ProductSales.objects.create(product_code=code, product_name=name, month=date(2026, 9, 1), total_sales=100)

    def test_partial_returns_only_the_table(self):
        r = self.client.get(reverse('product_sales'), {'tq': 'tip', 'year': '2026', 'partial': 'table'})
        html = r.content.decode()
        self.assertTrue(html.lstrip().startswith('{') is False and 'id="ps-table-body"' in html)
        self.assertIn('data-count="2" data-total="3"', html)
        self.assertNotIn('<canvas', html)
        self.assertNotIn('<html', html)
        self.assertIn('product=TT1', html)
        self.assertIn('year=2026', html)                      # product links keep the filters
        self.assertIn('name="next" value="/product-sales/?tq=tip&amp;year=2026#ps-table"', html)   # pins return to the page

    def test_page_has_live_search_hooks(self):
        html = self.client.get(reverse('product_sales')).content.decode()
        for text in ('id="ps-tsearch"', 'id="ps-tq"', 'id="ps-table-body"', "partial.set('partial', 'table')"):
            self.assertIn(text, html)

    def test_pin_only_redirects_within_the_site(self):
        r = self.client.post(reverse('product_sales_pin'), {'code': 'TT1', 'next': 'https://evil.example/'})
        self.assertEqual(r['Location'], reverse('product_sales'))
        r = self.client.post(reverse('product_sales_pin'), {'code': 'TT1', 'next': '/product-sales/?tq=tip#ps-table'})
        self.assertEqual(r['Location'], '/product-sales/?tq=tip#ps-table')


class QuickLinkOrderTests(TestCase):
    """Same data as the colour tests: G1 120%, O1 95%, R1 50%, N1 no target; Drinks group 88%."""
    setUp = ProductTargetColourTests.setUp

    def test_one_list_lowest_first(self):
        page = self.client.get(reverse('product_sales'), {'lm': 9})
        order = [(q['kind'], q['name'], q['pct']) for q in page.context['quick']]
        self.assertEqual(order, [('product', 'Red Wine', 50), ('group', 'Drinks', 88), ('product', 'Orange Juice', 95),
                                 ('product', 'Green Tea', 120), ('product', 'New Snack', None)])
        html = page.content.decode()
        self.assertLess(html.index('>Red Wine<'), html.index('🗂 Drinks'))
        self.assertLess(html.index('🗂 Drinks'), html.index('>Green Tea<'))
        self.assertNotIn('Pinned products ·', html)


class QuickLinkStatusButtonTests(TestCase):
    setUp = ProductTargetColourTests.setUp   # G1 reached, O1 and Drinks 70–99%, R1 below, N1 no target

    def test_buttons_with_counts_and_item_status(self):
        page = self.client.get(reverse('product_sales'), {'lm': 9})
        self.assertEqual(page.context['status_counts'], {'good': 1, 'close': 2, 'behind': 1})
        html = page.content.decode()
        for text in ('data-status="good" aria-pressed="false"', 'Reached <b>1</b>', '70–99% <b>2</b>', 'Below 70% <b>1</b>',
                     '<div class="ps-item" data-status="behind">', '<div class="ps-item" data-status="none">'):
            self.assertIn(text, html)


class QuickLinkMonthTests(TestCase):
    """The quick links are judged on the current month by default, and any month can be picked."""
    def setUp(self):
        from .models import PinnedProduct, ProductSales
        _manager('office')
        self.client.login(username='office', password='pw')
        self.year = date.today().year
        ProductSales.objects.create(product_code='CK1', product_name='Coke', month=date(self.year - 1, 1, 1), total_sales=1000)
        ProductSales.objects.create(product_code='CK1', product_name='Coke', month=date(self.year, 1, 1), total_sales=800)
        PinnedProduct.objects.create(product_code='CK1')

    def test_defaults_to_current_month_even_before_upload(self):
        from .product_sales import MONTHS
        page = self.client.get(reverse('product_sales'))
        this_month = f'{MONTHS[date.today().month - 1]} {self.year}'
        self.assertEqual(page.context['link_month'], this_month)
        self.assertEqual(page.context['link_month_i'], date.today().month)
        if date.today().month != 1:
            self.assertContains(page, f'no {this_month} sales uploaded yet')

    def test_pick_another_month(self):
        page = self.client.get(reverse('product_sales'), {'lm': 1, 'category': 'x'})
        self.assertEqual(page.context['link_month'], f'Jan {self.year}')
        self.assertIn(('category', 'x'), page.context['link_month_keep'])   # other filters stay
        self.assertNotIn('sales uploaded yet', page.content.decode())
        self.assertIn('lm=1', page.context['keep_query'])   # clicking a quick link keeps the month
        link = self.client.get(reverse('product_sales'), {'lm': 1}).context['links'][0]
        self.assertEqual((link['month_sales'], link['target'], link['pct']), (800, 1000, 80))
        self.assertEqual(self.client.get(reverse('product_sales'), {'lm': 'bad'}).context['link_month_i'], date.today().month)


class ClientListSalesColumnTests(TestCase):
    def test_total_sales_column_replaces_phone_and_photos(self):
        from .models import MonthlySales, Shop, ShopPhoto
        _manager('office')
        self.client.login(username='office', password='pw')
        year = date.today().year
        big = Shop.objects.create(name='Big Store', phone='7771234')
        small = Shop.objects.create(name='Small Store')
        Shop.objects.create(name='No Sales Store')
        for shop, amounts in ((big, (5000, 7000)), (small, (300,))):
            for i, amount in enumerate(amounts, start=1):
                MonthlySales.objects.create(shop=shop, month=date(year, i, 1), sales=amount)
        MonthlySales.objects.create(shop=small, month=date(year - 1, 12, 1), sales=99999)   # last year isn't counted
        for _ in range(2):   # photos must not double the total
            ShopPhoto.objects.create(shop=big, image='x.jpg')

        page = self.client.get(reverse('shop_list'), {'sort': 'sales', 'photos': 'yes'})
        self.assertEqual([(s.name, s.total_sales) for s in page.context['page_obj']], [('Big Store', 12000)])
        rows = self.client.get(reverse('shop_list'), {'sort': 'sales'}).context['page_obj']
        self.assertEqual([(s.name, s.total_sales) for s in rows], [('Big Store', 12000), ('Small Store', 300), ('No Sales Store', None)])
        html = self.client.get(reverse('shop_list')).content.decode()
        self.assertIn(f'Total Sales {year}', html)
        self.assertNotIn('<th>Phone</th>', html)
        self.assertNotIn('<th>Photos</th>', html)
        self.assertIn('12,000', html)


class SalesRepAdminTests(TestCase):
    """Reps live in the database (seeded with Grace, Ruth, Judane, Ivan) and are edited in the admin."""
    def setUp(self):
        from .models import Shop
        User.objects.create_superuser('admin', password='pw')
        self.client.login(username='admin', password='pw')
        for code, ctype in (('M1', 'Government / Ministries'), ('B1', 'Banks'), ('C1', 'Corporation'), ('R1', 'Retail / Supermarkets')):
            Shop.objects.create(customer_code=code, name=f'Client {code}', customer_type=ctype)

    def test_seeded_reps_match_as_before(self):
        from .models import SalesRep
        from . import corporate
        self.assertEqual(list(SalesRep.objects.values_list('name', flat=True)), ['Grace', 'Ruth', 'Judane', 'Ivan'])
        ids, types, unmatched = corporate.client_ids_by_manager()
        self.assertEqual((sorted(types['ruth']), unmatched), (['Banks', 'Government / Ministries'], ['Corporation']))

    def test_editing_a_rep_changes_the_page(self):
        from .models import SalesRep
        from . import corporate
        ruth = SalesRep.objects.get(key='ruth')
        ruth.name, ruth.customer_types, ruth.color = 'Ruth T.', ruth.customer_types + ', corporation', '#123456'
        ruth.save()
        SalesRep.objects.filter(key='ivan').update(active=False)
        SalesRep.objects.create(key='sam', name='Sam', streams='Schools', customer_types='school', order=9)
        ms, unmatched = corporate.year_summary(date.today().year)
        self.assertEqual([m['name'] for m in ms], ['Grace', 'Ruth T.', 'Judane', 'Sam'])
        self.assertEqual((ms[1]['client_count'], ms[1]['color'], unmatched), (3, '#123456', ['Retail / Supermarkets']))
        page = self.client.get(reverse('corporate_sales')).content.decode()
        self.assertIn('id="slide-sam"', page)
        self.assertNotIn('id="slide-ivan"', page)
        self.assertEqual(self.client.get(reverse('corporate_manager', args=['ivan'])).status_code, 404)

    def test_admin_pages(self):
        from .models import SalesRep
        listing = self.client.get(reverse('admin:shops_salesrep_changelist'))
        self.assertContains(listing, 'Grace')
        ruth = SalesRep.objects.get(key='ruth')
        change = self.client.get(reverse('admin:shops_salesrep_change', args=[ruth.pk]))
        self.assertContains(change, '2 client(s): Banks, Government / Ministries')
        self.assertContains(change, 'type="color"')
        add_target = self.client.get(reverse('admin:shops_salestarget_add'))
        self.assertContains(add_target, '<option value="ruth">Ruth</option>')
        r = self.client.post(reverse('admin:shops_salestarget_add'), {'manager': 'ruth', 'month': '2026-10-15', 'amount': '5000'})
        self.assertEqual(r.status_code, 302)
        from .models import SalesTarget
        self.assertEqual(str(SalesTarget.objects.get(manager='ruth').month), '2026-10-01')


class DashboardCorporateChartTests(TestCase):
    def test_corporate_sales_by_type(self):
        import json
        from .models import MonthlySales, Shop
        _manager('office')
        self.client.login(username='office', password='pw')
        year = date.today().year
        for code, ctype, amount in (('H1', 'HORECA', 5000), ('H2', 'HORECA', 3000), ('M1', 'Government / Ministries', 9000),
                                    ('N1', 'NGOs', None), ('R1', 'Corporation', 99999)):
            shop = Shop.objects.create(customer_code=code, name=code, customer_type=ctype)
            if amount:
                MonthlySales.objects.create(shop=shop, month=date(year, 1, 1), sales=amount)
        page = self.client.get(reverse('dashboard'))
        data = json.loads(page.context['biz_data'])
        self.assertEqual([(d['label'], d['value'], d['rep'], d['clients']) for d in data],
                         [('Government / Ministries', 9000.0, 'Ruth', 1), ('HORECA', 8000.0, 'Judane', 2), ('NGOs', 0.0, 'Grace', 1)])
        self.assertContains(page, f'Corporate Sales by Type · {year}')


class AccessLevelTests(TestCase):
    """Sales, Marketing and Manager each open only their areas; only Managers can download anything."""

    def login_as(self, role):
        from django.contrib.auth.models import Group
        user = User.objects.create_user(role.lower(), password='pw')
        user.groups.add(Group.objects.get(name=role))
        self.client.login(username=role.lower(), password='pw')

    def status(self, name, *args, query=''):
        return self.client.get(reverse(name, args=args) + query).status_code

    def test_sales(self):
        self.login_as('Sales')
        for name in ('dashboard', 'shop_list', 'corporate_sales', 'business_list', 'atlas'):
            self.assertEqual(self.status(name), 200, name)
        for name in ('product_sales', 'promotion_list', 'sponsorship_list', 'fe_order_list', 'product_list',
                     'monthly_sales', 'survey_list', 'reports', 'import_shops', 'import_sponsorships'):
            self.assertEqual(self.status(name), 403, name)
        page = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn(reverse('promotion_list'), page)
        self.assertNotIn(reverse('import_shops'), page)
        self.assertIn(reverse('corporate_sales'), page)

    def test_marketing(self):
        self.login_as('Marketing')
        for name in ('dashboard', 'shop_list', 'promotion_list', 'sponsorship_list',
                     'fe_order_list', 'product_list', 'survey_list'):
            self.assertEqual(self.status(name), 200, name)
        for name in ('corporate_sales', 'business_list', 'product_sales', 'monthly_sales', 'reports',
                     'import_shops', 'import_monthly_sales', 'product_import'):
            self.assertEqual(self.status(name), 403, name)
        self.assertEqual(self.status('corporate_manager', 'all'), 403)
        page = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn(reverse('corporate_sales'), page)
        self.assertNotIn('Total Sales', self.client.get(reverse('shop_list')).content.decode())

    def test_marketing_can_import_surveys_only(self):
        from .models import Survey
        self.login_as('Marketing')
        survey = Survey.objects.create(title='Soda')
        self.assertEqual(self.status('import_surveys'), 200)
        self.assertEqual(self.status('import_survey_responses', survey.pk), 200)
        self.assertEqual(self.status('download_survey_template'), 403)
        for name in ('import_shops', 'import_businesses', 'import_sponsorships', 'import_product_sales'):
            self.assertEqual(self.status(name), 403, name)
        self.assertContains(self.client.get(reverse('survey_list')), reverse('import_surveys'))
        page = self.client.get(reverse('import_surveys')).content.decode()
        self.assertIn('<th>Customer/Shop</th>', page)
        self.assertNotIn(reverse('download_survey_template'), page)

    def test_sales_cannot_import_surveys(self):
        self.login_as('Sales')
        self.assertEqual(self.status('import_surveys'), 403)

    def test_sales_and_marketing_cannot_download(self):
        for role in ('Sales', 'Marketing'):
            self.login_as(role)
            for name in ('download_report', 'product_sales_export', 'product_export', 'sales_export',
                         'download_shop_template', 'product_template'):
                self.assertEqual(self.status(name, query='?type=promotions'), 403, (role, name))
            self.assertEqual(self.status('shop_list', query='?export=1'), 403, role)
            for name in ('shop_list', 'sponsorship_list', 'promotion_list', 'product_list', 'fe_order_list'):
                if self.status(name) == 200:
                    page = self.client.get(reverse(name)).content.decode()
                    self.assertNotIn('Export CSV', page, (role, name))
                    self.assertNotIn(reverse('download_report'), page, (role, name))
                    self.assertNotIn(reverse('sales_export'), page, (role, name))
            self.client.logout()

    def test_manager_opens_and_downloads_everything(self):
        self.login_as('Manager')
        for name in ('corporate_sales', 'product_sales', 'promotion_list', 'sponsorship_list', 'fe_order_list',
                     'monthly_sales', 'survey_list', 'reports', 'import_shops'):
            self.assertEqual(self.status(name), 200, name)
        response = self.client.get(reverse('download_report') + '?type=promotions')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])

    def test_no_access_level_gets_only_shared_areas(self):
        User.objects.create_user('nobody', password='pw')
        self.client.login(username='nobody', password='pw')
        self.assertEqual(self.status('shop_list'), 200)
        for name in ('corporate_sales', 'promotion_list', 'reports'):
            self.assertEqual(self.status(name), 403, name)


class RepCorporateSalesTests(TestCase):
    """A rep (e.g. Grace) sees only their own stream, plus every rep's % of this month's target."""

    def setUp(self):
        from django.contrib.auth.models import Group
        from .models import MonthlySales, SalesRep, SalesTarget, Shop
        SalesRep.objects.all().delete()
        self.grace_user = User.objects.create_user('grace', password='pw')
        self.grace_user.groups.add(Group.objects.get(name='Sales'))
        SalesRep.objects.create(key='grace', name='Grace', streams='Ministries', customer_types='ministr',
                                color='#7C3AED', order=1, user=self.grace_user)
        SalesRep.objects.create(key='ruth', name='Ruth', streams='Banks', customer_types='bank', color='#0EA5E9', order=2)
        month = date.today().replace(day=1)
        for key, ctype, sale, target in (('grace', 'Ministry', 500, 1000), ('ruth', 'Bank', 777, 1000)):
            shop = Shop.objects.create(name=f'{key} client', customer_code=key.upper(), customer_type=ctype, island='Upolu')
            MonthlySales.objects.create(shop=shop, month=month, sales=sale)
            SalesTarget.objects.create(manager=key, month=month, amount=target)
        self.client.login(username='grace', password='pw')

    def test_only_own_slide_but_everyones_month_percent(self):
        page = self.client.get(reverse('corporate_sales')).content.decode()
        self.assertIn('id="slide-grace"', page)
        self.assertNotIn('id="slide-ruth"', page)
        self.assertIn('50%', page)      # Grace: 500 of 1000
        self.assertIn('78%', page)      # Ruth's card: 777 of 1000
        self.assertNotIn('777', page)   # but not Ruth's amounts
        self.assertNotIn(reverse('corporate_targets'), page)

    def test_other_reps_pages_and_targets_are_blocked(self):
        self.assertEqual(self.client.get(reverse('corporate_manager', args=['grace'])).status_code, 200)
        self.assertEqual(self.client.get(reverse('corporate_manager', args=['ruth'])).status_code, 403)
        self.assertRedirects(self.client.get(reverse('corporate_manager', args=['all'])),
                             reverse('corporate_manager', args=['grace']))
        self.assertEqual(self.client.get(reverse('corporate_targets')).status_code, 403)

    def test_dashboard_chart_only_has_own_stream(self):
        page = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('Ministry', page)
        self.assertNotIn('"Bank"', page)

    def test_manager_still_sees_everyone(self):
        self.grace_user.groups.clear()
        from django.contrib.auth.models import Group
        self.grace_user.groups.add(Group.objects.get(name='Manager'))
        page = self.client.get(reverse('corporate_sales')).content.decode()
        self.assertIn('id="slide-ruth"', page)


class CustomerProductChartTests(TestCase):
    """Top 10 products on Corporate Sales: from the Customer Product Sales upload, per rep and per top client."""

    def setUp(self):
        from .models import MonthlySales, SalesRep, Shop
        SalesRep.objects.all().delete()
        SalesRep.objects.create(key='grace', name='Grace', streams='Ministries', customer_types='ministr', order=1)
        self.year = date.today().year
        month = date(self.year, 1, 1)
        self.health = Shop.objects.create(name='Ministry of Health', customer_code='C1', customer_type='Ministry')
        self.works = Shop.objects.create(name='Ministry of Works', customer_code='C2', customer_type='Ministry')
        for shop in (self.health, self.works):
            MonthlySales.objects.create(shop=shop, month=month, sales=1000)
        _manager('office')
        self.client.login(username='office', password='pw')

    def upload(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(reverse('import_customer_product_sales'),
                                {'csv_file': SimpleUploadedFile('cps.csv', text.encode())})

    def test_upload_matches_clients_and_replaces_months(self):
        from .models import CustomerProductSales
        yy = f'{self.year % 100:02d}-01'
        head = 'Customer Code,Customer Name,Product Code,Product Name,Date (YY-MM),Sales\n'
        self.upload(head + f'C1,Health,P1,Milk,{yy},100\nC1,Health,P2,Bread,{yy},50\nC9,Nobody,P1,Milk,{yy},5\n')
        self.assertEqual(CustomerProductSales.objects.count(), 2)
        response = self.upload(head + f'C1,Health,P1,Milk,{yy},120\n')
        self.assertEqual(CustomerProductSales.objects.count(), 2)
        self.assertEqual(CustomerProductSales.objects.get(product_code='P1').sales, 120)
        self.assertEqual(response.status_code, 200)

    def test_chart_data_for_rep_and_each_top_client(self):
        import json as _json
        from .models import CustomerProductSales
        month = date(self.year, 1, 1)
        for shop, code, name, amount in ((self.health, 'P1', 'Milk', 300), (self.health, 'P2', 'Bread', 100),
                                         (self.works, 'P2', 'Bread', 500)):
            CustomerProductSales.objects.create(shop=shop, product_code=code, product_name=name, month=month, sales=amount)
        response = self.client.get(reverse('corporate_sales'))
        data = _json.loads(response.context['chart_data'])['managers'][0]['products']
        self.assertEqual([(r['name'], r['value']) for r in data['all']], [('Bread', 600.0), ('Milk', 300.0)])
        self.assertEqual([r['name'] for r in data[str(self.health.pk)]], ['Milk', 'Bread'])
        self.assertEqual([r['name'] for r in data[str(self.works.pk)]], ['Bread'])
        page = response.content.decode()
        self.assertIn(f'data-shop="{self.health.pk}"', page)
        self.assertIn('Top 10 products', page)


class SurveyCSVImportTests(TestCase):
    def setUp(self):
        self.client.force_login(_manager('boss'))

    def upload(self, text, **data):
        from django.core.files.uploadedfile import SimpleUploadedFile
        data['csv_file'] = SimpleUploadedFile('survey.csv', text.encode())
        return self.client.post(reverse('import_surveys'), data)

    def test_list_has_import_button_and_page_shows_template(self):
        self.assertContains(self.client.get(reverse('survey_list')), reverse('import_surveys'))
        page = self.client.get(reverse('import_surveys'))
        self.assertContains(page, '<th>Customer/Shop</th>')
        self.assertContains(page, 'Samoa Store')

    def test_import_into_new_survey(self):
        from .models import Survey
        self.upload('Products,Customer/Shop,Period,Price,QTY,Location,Region\n'
                    'Coke,Samoa Store,May-26,2.50,"1,200",Apia,REGION 1\nFanta,,,,,,\n,,,,,,\n',
                    new_title='Soda check', new_category='Market Research')
        survey = Survey.objects.get(title='Soda check')
        self.assertEqual(survey.category, 'Market Research')
        self.assertEqual(survey.responses.count(), 2)
        coke = survey.responses.get(product='Coke')
        self.assertEqual((coke.customer, coke.period, float(coke.price), coke.quantity, coke.location, coke.region),
                         ('Samoa Store', 'May-26', 2.5, 1200, 'Apia', 'REGION 1'))

    def test_import_into_existing_survey(self):
        from .models import Survey
        survey = Survey.objects.create(title='Existing')
        self.upload('Products,Period\nCoke,Jun-26\n', survey=survey.pk)
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(survey.responses.get().period, 'Jun-26')

    def test_detail_and_analysis_pages_render(self):
        from .models import Survey, SurveyResponse
        survey = Survey.objects.create(title='Pages')
        SurveyResponse.objects.create(survey=survey, product='Coke', customer='Shop A', period='May-26',
                                      price=3, quantity=10, location='Apia', region='1')
        self.assertContains(self.client.get(reverse('survey_detail', args=[survey.pk])), 'May-26')
        self.assertContains(self.client.get(reverse('survey_analysis', args=[survey.pk])), 'Store reach')
        self.assertContains(self.client.get(reverse('add_survey_response', args=[survey.pk])), 'Customer/Shop')

    def test_needs_survey_or_title(self):
        from .models import Survey
        response = self.upload('Products\nCoke\n')
        self.assertContains(response, 'Pick an existing survey')
        self.assertEqual(Survey.objects.count(), 0)


class SurveyAnalysisTests(TestCase):
    def setUp(self):
        from .models import Survey, SurveyResponse
        self.client.force_login(_manager('boss'))
        self.survey = Survey.objects.create(title='Soda')
        for product, store, price, region in (('Coke', 'A', 3, '1'), ('Coke', 'B', 4, '1'), ('Coke', 'C', 5, '2'),
                                              ('Fanta', 'A', 2, '1'), ('Fanta', 'A', 2.5, '1')):
            SurveyResponse.objects.create(survey=self.survey, product=product, customer=store, price=price,
                                          quantity=10, region=region, period='May-26')
        SurveyResponse.objects.create(survey=self.survey, product='Coke', customer='C', price=6, region='2', period='Jun-26')

    def data(self, **params):
        return self.client.get(reverse('survey_analysis', args=[self.survey.pk]), params).context['chart_data']

    def test_brand_reach_and_prices(self):
        data = self.data()
        coke, fanta = data['brands']
        self.assertEqual((coke['name'], coke['stores'], coke['pct'], coke['max_price'], coke['min_price']),
                         ('Coke', 3, 100.0, 6.0, 3.0))
        self.assertEqual((fanta['stores'], fanta['pct'], fanta['max_price'], fanta['min_price']), (1, 33.3, 2.5, 2.0))
        self.assertEqual([s['name'] for s in data['stores']], ['A', 'B', 'C'])
        self.assertEqual([p['name'] for p in data['periods']], ['May-26', 'Jun-26'])

    def test_filters_scope_every_chart(self):
        data = self.data(region='2')
        self.assertEqual(data['store_total'], 1)
        self.assertEqual([(b['name'], b['pct']) for b in data['brands']], [('Coke', 100.0)])

    def test_png_button_for_everyone_who_can_open_analysis(self):
        from django.contrib.auth.models import Group
        marketing = User.objects.create_user('mk', password='pw')
        marketing.groups.add(Group.objects.get(name='Marketing'))
        self.client.force_login(marketing)
        response = self.client.get(reverse('survey_analysis', args=[self.survey.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '⬇ PNG')


class SurveyDeleteTests(TestCase):
    def test_list_links_to_delete_and_post_removes_survey_with_responses(self):
        from .models import Survey, SurveyResponse
        self.client.force_login(_manager('boss'))
        survey = Survey.objects.create(title='Old')
        SurveyResponse.objects.create(survey=survey, product='Coke')
        self.assertContains(self.client.get(reverse('survey_list')), reverse('delete_survey', args=[survey.pk]))
        self.assertContains(self.client.get(reverse('delete_survey', args=[survey.pk])), 'cannot be undone')
        self.assertEqual(Survey.objects.count(), 1)  # GET only asks for confirmation
        self.assertRedirects(self.client.post(reverse('delete_survey', args=[survey.pk])), reverse('survey_list'))
        self.assertFalse(Survey.objects.exists())
        self.assertFalse(SurveyResponse.objects.exists())
