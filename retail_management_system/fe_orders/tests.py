import csv
import json
import urllib.error
import os
import shutil
import tempfile
from datetime import date
from io import BytesIO
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from shops.models import Shop

from .models import Issue, Order, Product

TELEGRAM_ON = {'BOT_TOKEN': '123:tok', 'CHAT_ID': '-1001234'}


class InlineThread:
    """Run the Telegram send immediately instead of in a background thread."""
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class FEBase(TestCase):
    def setUp(self):
        # Daily sales files go to a throwaway folder, never the real exports/ folder
        self.export_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.export_dir, ignore_errors=True)
        # never send real Telegram messages or emails from tests, whatever is in .env
        patcher = override_settings(SALES_EXPORT_DIR=self.export_dir, TELEGRAM={}, OFFICE365={})
        patcher.enable()
        self.addCleanup(patcher.disable)
        self.fe = User.objects.create_user('sione', password='pw')
        self.fe.groups.add(Group.objects.get(name='fe_boys'))
        self.fe2 = User.objects.create_user('tavita', password='pw')
        self.fe2.groups.add(Group.objects.get(name='fe_boys'))
        self.office = User.objects.create_user('office', password='pw')
        self.office.groups.add(Group.objects.get(name='Manager'))
        self.shop = Shop.objects.create(name='Jane Store', address='LALOVAEA', phone='7771234', territory='EC2')
        self.coke = Product.objects.create(name='Coke Can 330ml', category='Soda', unit='Carton of 24', unit_price='28.50')
        self.water = Product.objects.create(name='Aqua Water 1.5L', category='Water', available=False)

    def place(self, items, **extra):
        data = {'shop_id': self.shop.id, 'address': 'Lalovaea', 'phone': '7771234',
                'items': json.dumps([{'product': p.id, 'qty': q} for p, q in items])}
        data.update(extra)
        return self.client.post(reverse('fe_place_order'), data)


class AccessTests(FEBase):
    def test_fe_user_is_kept_to_fe_screens(self):
        self.client.login(username='sione', password='pw')
        for name in ('dashboard', 'shop_list', 'product_list', 'reports'):
            self.assertRedirects(self.client.get(reverse(name)), reverse('fe_home'), msg_prefix=name)
        for name in ('fe_home', 'fe_place_order', 'fe_order_list', 'fe_issue_list', 'fe_report_issue', 'atlas'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_office_user_sees_everything(self):
        self.client.login(username='office', password='pw')
        for name in ('dashboard', 'product_list', 'fe_home', 'fe_order_list'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_home_has_four_buttons(self):
        self.client.login(username='sione', password='pw')
        html = self.client.get(reverse('fe_home')).content.decode()
        for label in ('Place Order', 'Ah Liki Atlas', 'View Orders', 'Issues'):
            self.assertIn(label, html)


class OrderTests(FEBase):
    def setUp(self):
        super().setUp()
        self.client.login(username='sione', password='pw')

    def test_place_order(self):
        r = self.place([(self.coke, 3)], notes='Deliver Friday')
        order = Order.objects.get()
        self.assertRedirects(r, reverse('fe_order_detail', args=[order.pk]) + '?placed=1')
        self.assertEqual(order.placed_by, self.fe)
        self.assertEqual(order.total, 85.50)
        self.assertEqual(order.telegram_status, 'Not configured')

    def test_rejects_out_of_stock_and_empty(self):
        self.place([(self.water, 2)])
        self.place([])
        self.assertFalse(Order.objects.exists())

    def test_fe_only_sees_own_orders_and_cannot_change_status(self):
        self.place([(self.coke, 1)])
        order = Order.objects.get()
        self.client.login(username='tavita', password='pw')
        self.assertEqual(self.client.get(reverse('fe_order_detail', args=[order.pk])).status_code, 404)
        self.client.login(username='sione', password='pw')
        self.client.post(reverse('fe_order_detail', args=[order.pk]), {'status': 'Delivered'})
        order.refresh_from_db()
        self.assertEqual(order.status, 'Pending')

    def test_office_can_change_status(self):
        self.place([(self.coke, 1)])
        order = Order.objects.get()
        self.client.login(username='office', password='pw')
        self.client.post(reverse('fe_order_detail', args=[order.pk]), {'status': 'Confirmed'})
        order.refresh_from_db()
        self.assertEqual(order.status, 'Confirmed')

    @override_settings(TELEGRAM=TELEGRAM_ON)
    def test_telegram_group_message(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true, "result": {"message_id": 7}}'
        with mock.patch('fe_orders.telegram.threading.Thread', InlineThread), \
             mock.patch('fe_orders.telegram.urllib.request.urlopen', return_value=response) as urlopen, \
             self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 3)])
        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, 'https://api.telegram.org/bot123:tok/sendMessage')
        body = json.loads(req.data)
        self.assertEqual((body['chat_id'], body['parse_mode']), ('-1001234', 'HTML'))
        self.assertIn('<b>Shop:</b> Jane Store (EC2)', body['text'])
        self.assertIn('3 × Coke Can 330ml', body['text'])
        self.assertIn('WST 85.50', body['text'])
        self.assertEqual(Order.objects.get().telegram_status, 'Sent')

    @override_settings(TELEGRAM=TELEGRAM_ON)
    def test_telegram_failure_keeps_order(self):
        with mock.patch('fe_orders.telegram.threading.Thread', InlineThread), \
             mock.patch('fe_orders.telegram.urllib.request.urlopen', side_effect=OSError('no network')), \
             self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 1)])
        self.assertTrue(Order.objects.get().telegram_status.startswith('Failed'))

    @override_settings(TELEGRAM=TELEGRAM_ON)
    def test_telegram_error_reason_is_saved(self):
        import urllib.error
        err = urllib.error.HTTPError('https://api.telegram.org', 400, 'Bad Request', {},
                                     BytesIO(b'{"ok": false, "description": "Bad Request: chat not found"}'))
        with mock.patch('fe_orders.telegram.threading.Thread', InlineThread), \
             mock.patch('fe_orders.telegram.urllib.request.urlopen', side_effect=err), \
             self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 1)])
        self.assertEqual(Order.objects.get().telegram_status, 'Failed: Bad Request: chat not found')

    @override_settings(TELEGRAM=TELEGRAM_ON)
    def test_office_can_resend_failed_telegram(self):
        with mock.patch('fe_orders.telegram.threading.Thread', InlineThread), \
             mock.patch('fe_orders.telegram.urllib.request.urlopen', side_effect=OSError('no network')), \
             self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 1)])
        order = Order.objects.get()
        url = reverse('fe_order_detail', args=[order.pk])

        # FE staff don't get the resend action
        self.assertEqual(self.client.post(url, {'resend_telegram': '1'}).status_code, 404)

        self.client.login(username='office', password='pw')
        self.assertContains(self.client.get(url), 'Resend to Telegram')
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true, "result": {"message_id": 8}}'
        with mock.patch('fe_orders.telegram.threading.Thread', InlineThread), \
             mock.patch('fe_orders.telegram.urllib.request.urlopen', return_value=response) as urlopen, \
             self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {'resend_telegram': '1'})
        self.assertEqual(urlopen.call_count, 1)
        order.refresh_from_db()
        self.assertEqual(order.telegram_status, 'Sent')
        self.assertNotContains(self.client.get(url), 'Resend to Telegram')


class IssueTests(FEBase):
    def test_report_issue(self):
        self.client.login(username='sione', password='pw')
        self.client.post(reverse('fe_report_issue'), {'category': 'Fridge / Cooler', 'description': 'Not cooling',
                                                      'shop_id': self.shop.id})
        issue = Issue.objects.get()
        self.assertEqual((issue.shop, issue.reported_by, issue.status), (self.shop, self.fe, 'Open'))


class ProductImportTests(FEBase):
    def test_upload_creates_and_updates(self):
        self.client.login(username='office', password='pw')
        csv_text = ('name,category,unit,unit_price,available\n'
                    'Coke Can 330ml,,,30.00,FALSE\n'
                    'Taro Chips 50g,Snacks,Box of 20,15,\n'
                    'No Category Thing,,,,\n')
        f = SimpleUploadedFile('p.csv', csv_text.encode('utf-8-sig'), content_type='text/csv')
        result = self.client.post(reverse('product_import'), {'csv_file': f}).context['result']
        self.assertEqual((result['created'], result['updated'], len(result['errors'])), (1, 1, 1))
        self.coke.refresh_from_db()
        self.assertEqual((str(self.coke.unit_price), self.coke.available, self.coke.category), ('30.00', False, 'Soda'))
        self.assertTrue(Product.objects.get(name='Taro Chips 50g').available)

    def test_upload_sets_and_clears_quick_link(self):
        self.client.login(username='office', password='pw')
        self.water.quick_link = 'Drinks'
        self.water.save()
        csv_text = ('name,category,quick_link\n'
                    'Coke Can 330ml,,Tip Top\n'
                    'Aqua Water 1.5L,,NONE\n'
                    'Beef Mince 1kg,Frozen,Meat\n')
        f = SimpleUploadedFile('p.csv', csv_text.encode('utf-8-sig'), content_type='text/csv')
        result = self.client.post(reverse('product_import'), {'csv_file': f}).context['result']
        self.assertEqual((result['created'], result['updated'], len(result['errors'])), (1, 2, 0))
        self.assertEqual(Product.objects.get(name='Coke Can 330ml').quick_link, 'Tip Top')
        self.assertEqual(Product.objects.get(name='Aqua Water 1.5L').quick_link, '')
        self.assertEqual(Product.objects.get(name='Beef Mince 1kg').quick_link, 'Meat')

    def test_upload_with_office_headers(self):
        self.client.login(username='office', password='pw')
        self.coke.product_no = '10001'
        self.coke.save()
        csv_text = ('Product No,Product Name,Product Category,Unit of Measure Code,Cost,Unit Price,Unit Price Including VAT\n'
                    '10001,Coke Can 330ml (24),,CTN,22.00,"$1,028.50",32.78\n'   # matched by number and renamed
                    '10002,Tip Top Vanilla 2L,Ice Cream,EA,14,18.00,20.70\n'
                    '10003,Bad Price Thing,Snacks,EA,abc,,\n')
        f = SimpleUploadedFile('p.csv', csv_text.encode('utf-8-sig'), content_type='text/csv')
        result = self.client.post(reverse('product_import'), {'csv_file': f}).context['result']
        self.assertEqual((result['created'], result['updated'], len(result['errors'])), (1, 1, 1))
        self.assertIn('Cost "abc"', result['errors'][0])
        self.coke.refresh_from_db()
        self.assertEqual((self.coke.name, self.coke.unit, str(self.coke.cost), str(self.coke.unit_price),
                          str(self.coke.unit_price_incl_vat), self.coke.category),
                         ('Coke Can 330ml (24)', 'CTN', '22.00', '1028.50', '32.78', 'Soda'))
        tiptop = Product.objects.get(product_no='10002')
        self.assertEqual((tiptop.name, str(tiptop.cost)), ('Tip Top Vanilla 2L', '14.00'))

    def test_export_round_trips(self):
        self.client.login(username='office', password='pw')
        exported = self.client.get(reverse('product_export')).content
        self.assertTrue(exported.startswith(b'Product No,Product Name,Product Category,Unit of Measure Code,'
                                            b'Cost,Unit Price,Unit Price Including VAT'))
        f = SimpleUploadedFile('p.csv', exported, content_type='text/csv')
        result = self.client.post(reverse('product_import'), {'csv_file': f}).context['result']
        self.assertEqual((result['created'], result['updated'], result['unchanged'], len(result['errors'])), (0, 0, 2, 0))


class SalesExportTests(FEBase):
    def setUp(self):
        super().setUp()
        self.client.login(username='sione', password='pw')

    def _rows(self, path):
        with open(path, encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    def test_daily_file_saved_and_updated(self):
        self.coke.product_no = '10001'
        self.coke.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 3), (self.water_available(), 2)])
        path = os.path.join(self.export_dir, f'sales_{date.today():%Y-%m-%d}.csv')
        rows = self._rows(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]['Shop'], rows[0]['Product No'], rows[0]['Quantity'], rows[0]['Line Total (WST)'],
                          rows[0]['Status']), ('Jane Store', '10001', '3', '85.50', 'Pending'))

        # A status change rewrites the day's file
        order = Order.objects.get()
        self.client.login(username='office', password='pw')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('fe_order_detail', args=[order.pk]), {'status': 'Delivered'})
        self.assertEqual({r['Status'] for r in self._rows(path)}, {'Delivered'})

    def test_office_download_and_fe_blocked(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 1)])
        today = f'{date.today():%Y-%m-%d}'
        # FE staff are sent back to their home screen
        self.assertRedirects(self.client.get(reverse('sales_export')), reverse('fe_home'), fetch_redirect_response=False)

        self.client.login(username='office', password='pw')
        response = self.client.get(reverse('sales_export'), {'from': today, 'to': today, 'format': 'csv'})
        self.assertEqual(response['Content-Disposition'], f'attachment; filename="fe_orders_{today}.csv"')
        rows = list(csv.DictReader(response.content.decode('utf-8-sig').splitlines()))
        self.assertEqual([(r['Product'], r['Quantity']) for r in rows], [('Coke Can 330ml', '1')])
        empty = self.client.get(reverse('sales_export'), {'from': '2020-01-01', 'to': '2020-01-02', 'format': 'csv'})
        self.assertEqual(len(empty.content.decode('utf-8-sig').splitlines()), 1)   # header only

    def test_export_command_writes_past_days(self):
        from django.core.management import call_command
        call_command('export_sales', '--date', '2026-09-01', '--days', '2', stdout=open(os.devnull, 'w'))
        self.assertEqual(sorted(os.listdir(self.export_dir)), ['sales_2026-08-31.csv', 'sales_2026-09-01.csv'])

    def water_available(self):
        self.water.available = True
        self.water.save()
        return self.water


OFFICE365_ON = {'TENANT_ID': 'tenant-1', 'CLIENT_ID': 'app-1', 'CLIENT_SECRET': 'secret', 'SENDER': 'orders@ahliki.ws',
                'ORDER_EMAILS': 'office@ahliki.ws; boss@ahliki.ws', 'ISSUE_EMAILS': 'support@ahliki.ws'}


def graph_responses(*bodies):
    """Fake urlopen results, one per call (token request, then sendMail, …)."""
    out = []
    for body in bodies:
        r = mock.MagicMock()
        r.__enter__.return_value.read.return_value = body
        out.append(r)
    return out


class Office365Tests(FEBase):
    def setUp(self):
        super().setUp()
        from fe_orders import office365
        office365._token.update(value=None, expires=0)
        self.client.login(username='sione', password='pw')

    def test_order_email_is_sent_through_graph(self):
        with override_settings(OFFICE365=OFFICE365_ON), \
             mock.patch('fe_orders.office365.threading.Thread', InlineThread), \
             mock.patch('fe_orders.office365.urllib.request.urlopen',
                        side_effect=graph_responses(b'{"access_token": "tok-123", "expires_in": 3600}', b'')) as urlopen, \
             self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 3)], notes='Back door')
        token_req, mail_req = [c[0][0] for c in urlopen.call_args_list]
        self.assertEqual(token_req.full_url, 'https://login.microsoftonline.com/tenant-1/oauth2/v2.0/token')
        self.assertIn(b'grant_type=client_credentials', token_req.data)
        self.assertEqual(mail_req.full_url, 'https://graph.microsoft.com/v1.0/users/orders%40ahliki.ws/sendMail')
        self.assertEqual(mail_req.get_header('Authorization'), 'Bearer tok-123')
        msg = json.loads(mail_req.data)['message']
        self.assertEqual([r['emailAddress']['address'] for r in msg['toRecipients']], ['office@ahliki.ws', 'boss@ahliki.ws'])
        self.assertTrue(msg['subject'].startswith('New FE order ORD-') and msg['subject'].endswith('Jane Store'))
        for text in ('3 ×', 'Coke Can 330ml', 'WST 85.50', 'Back door', 'Open the order'):
            self.assertIn(text, msg['body']['content'])
        self.assertEqual(Order.objects.get().email_status, 'Sent')

    def test_failure_keeps_microsofts_reason_and_office_can_resend(self):
        err = urllib.error.HTTPError('https://graph', 403, 'Forbidden', {},
                                     BytesIO(b'{"error": {"code": "ErrorAccessDenied", "message": "Access is denied."}}'))
        with override_settings(OFFICE365=OFFICE365_ON), \
             mock.patch('fe_orders.office365.threading.Thread', InlineThread), \
             mock.patch('fe_orders.office365.urllib.request.urlopen',
                        side_effect=graph_responses(b'{"access_token": "t", "expires_in": 3600}') + [err]), \
             self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 1)])
        order = Order.objects.get()
        self.assertEqual(order.email_status, 'Failed: HTTP 403: Access is denied.')
        url = reverse('fe_order_detail', args=[order.pk])
        self.client.login(username='office', password='pw')
        self.assertContains(self.client.get(url), 'Resend email')
        with override_settings(OFFICE365=OFFICE365_ON), \
             mock.patch('fe_orders.office365.threading.Thread', InlineThread), \
             mock.patch('fe_orders.office365.urllib.request.urlopen', side_effect=graph_responses(b'')) as urlopen, \
             self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {'resend_email': '1'})
        self.assertEqual(urlopen.call_count, 1)   # the sign-in token was reused
        order.refresh_from_db()
        self.assertEqual(order.email_status, 'Sent')

    def test_not_configured_and_issue_emails(self):
        self.place([(self.coke, 1)])
        self.assertEqual(Order.objects.get().email_status, 'Not configured')
        with override_settings(OFFICE365=OFFICE365_ON), \
             mock.patch('fe_orders.office365.threading.Thread', InlineThread), \
             mock.patch('fe_orders.office365.urllib.request.urlopen',
                        side_effect=graph_responses(b'{"access_token": "t", "expires_in": 3600}', b'')) as urlopen, \
             self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('fe_report_issue'), {'category': 'Fridge / Cooler', 'description': 'Fridge is warm',
                                                          'shop_id': self.shop.id})
        msg = json.loads(urlopen.call_args_list[1][0][0].data)['message']
        self.assertEqual((msg['subject'], msg['toRecipients'][0]['emailAddress']['address']),
                         ('New FE issue: Fridge / Cooler — Jane Store', 'support@ahliki.ws'))
        self.assertIn('Fridge is warm', msg['body']['content'])
        self.assertEqual(Issue.objects.get().email_status, 'Sent')

    def test_html_in_names_is_escaped(self):
        from fe_orders import office365
        self.shop.name = '<b>Evil</b> Store'
        self.shop.save()
        self.place([(self.coke, 1)])
        subject, body = office365.order_email(Order.objects.get(), 'https://x/orders/1/')
        self.assertIn('&lt;b&gt;Evil&lt;/b&gt; Store', body)
        self.assertNotIn('<b>Evil</b>', body)


class OrderDownloadTests(FEBase):
    def setUp(self):
        super().setUp()
        self.client.login(username='sione', password='pw')
        self.shop2 = Shop.objects.create(name='Sam Mart', territory='TWN', customer_code='C002')
        with self.captureOnCommitCallbacks(execute=True):
            self.place([(self.coke, 2)])
            self.place([(self.coke, 1)], shop_id=self.shop2.id)
            self.place([(self.coke, 5)])
        Order.objects.filter(pk=Order.objects.order_by('pk').last().pk).update(status='Cancelled')
        self.client.login(username='office', password='pw')

    def book(self, **params):
        from openpyxl import load_workbook
        r = self.client.get(reverse('sales_export'), params)
        self.assertIn('.xlsx', r['Content-Disposition'])
        return load_workbook(BytesIO(r.content)), r

    def test_today_workbook_has_every_shop(self):
        wb, r = self.book(period='today')
        self.assertIn(f'fe_orders_{date.today():%Y-%m-%d}.xlsx', r['Content-Disposition'])
        self.assertEqual(wb.sheetnames, ['Orders', 'Order lines', 'By shop', 'By day'])
        orders = list(wb['Orders'].iter_rows(min_row=2, values_only=True))
        self.assertEqual(sorted((o[4], o[9], o[10], o[3]) for o in orders),
                         [('Jane Store', 2, 57.0, 'Pending'), ('Jane Store', 5, 142.5, 'Cancelled'), ('Sam Mart', 1, 28.5, 'Pending')])
        by_shop = list(wb['By shop'].iter_rows(min_row=2, values_only=True))
        self.assertEqual([(s[0], s[3], s[5]) for s in by_shop], [('Jane Store', 2, 199.5), ('Sam Mart', 1, 28.5)])
        by_day = list(wb['By day'].iter_rows(min_row=2, values_only=True))
        self.assertEqual(by_day[-1], ('TOTAL', 3, 2, 8, 228.0))
        self.assertEqual(wb['Order lines'].max_row, 4)

    def test_skip_cancelled_and_all_orders(self):
        wb, _ = self.book(period='all', skip_cancelled='1')
        self.assertEqual(wb['Orders'].max_row, 3)   # header + the 2 orders still going ahead
        wb, r = self.book(period='all')
        self.assertIn('fe_orders_all.xlsx', r['Content-Disposition'])
        self.assertEqual(wb['Orders'].max_row, 4)
        wb, _ = self.book(period='yesterday')
        self.assertEqual(wb['Orders'].max_row, 1)   # headers only

    def test_period_dates(self):
        from fe_orders.sales_export import period_dates
        wed = date(2026, 9, 30)
        self.assertEqual(period_dates('week', wed)[:2], (date(2026, 9, 28), wed))
        self.assertEqual(period_dates('month', wed)[:2], (date(2026, 9, 1), wed))
        self.assertEqual(period_dates('yesterday', wed)[:2], (date(2026, 9, 29), date(2026, 9, 29)))

    def test_page_offers_quick_downloads_fe_staff_do_not(self):
        page = self.client.get(reverse('fe_order_list')).content.decode()
        for key in ('today', 'yesterday', 'week', 'month', 'all'):
            self.assertIn(f'?period={key}', page)
        self.client.login(username='sione', password='pw')
        self.assertNotIn('?period=today', self.client.get(reverse('fe_order_list')).content.decode())
