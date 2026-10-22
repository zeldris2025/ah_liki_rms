from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Booking, Notification
from .notify import car_recipients as notify_recipients


def _fmt(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')


@override_settings(OFFICE365={})
class CarBookingTests(TestCase):
    def setUp(self):
        self.sales = User.objects.create_user('sione', email='sione@example.com', password='x')
        self.sales.groups.add(Group.objects.get_or_create(name='Sales')[0])
        self.marketing = User.objects.create_user('mele', email='mele@example.com', password='x')
        self.marketing.groups.add(Group.objects.get_or_create(name='Marketing')[0])
        self.start = (timezone.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    def book(self, user, car='81', start=None, hours=2, reason='Shop visits'):
        self.client.force_login(user)
        start = start or self.start
        return self.client.post(reverse('car_book'), {
            'car': car, 'start': _fmt(start), 'end': _fmt(start + timedelta(hours=hours)), 'reason': reason})

    def test_page_opens_for_sales_and_marketing(self):
        for user in (self.sales, self.marketing):
            self.client.force_login(user)
            self.assertContains(self.client.get(reverse('car_allocations')), 'Car Allocations')

    def test_booking_notifies_everyone_else(self):
        r = self.book(self.sales)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.marketing).count(), 1)
        self.assertFalse(Notification.objects.filter(recipient=self.sales).exists())
        self.assertEqual(Booking.objects.get().email_status, 'Not configured')

    def test_overlapping_booking_is_refused(self):
        self.book(self.sales)
        r = self.book(self.marketing, start=self.start + timedelta(hours=1))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(len(r.json()['clashes']), 1)
        self.assertEqual(Booking.objects.count(), 1)

    def test_back_to_back_and_other_cars_are_fine(self):
        self.book(self.sales)
        self.assertEqual(self.book(self.marketing, start=self.start + timedelta(hours=2)).status_code, 200)
        self.assertEqual(self.book(self.marketing, car='Ringo').status_code, 200)

    def test_bad_input(self):
        self.assertEqual(self.book(self.sales, hours=-1).status_code, 400)
        self.assertEqual(self.book(self.sales, reason='').status_code, 400)
        self.assertEqual(self.book(self.sales, car='Tesla').status_code, 400)
        self.assertEqual(self.book(self.sales, start=timezone.now() - timedelta(days=2)).status_code, 400)

    def test_week_and_search(self):
        self.book(self.sales, reason='Savaii promo run')
        monday = timezone.localtime(self.start).date() - timedelta(days=timezone.localtime(self.start).weekday())
        data = self.client.get(reverse('car_bookings'), {'start': monday.isoformat()}).json()
        self.assertEqual(len(data['bookings']), 1)
        self.assertEqual(len(self.client.get(reverse('car_booking_search'), {'q': 'savaii'}).json()['bookings']), 1)
        self.assertEqual(len(self.client.get(reverse('car_booking_search'), {'q': 'upolu'}).json()['bookings']), 0)

    def test_only_owner_can_cancel(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        self.client.force_login(self.marketing)
        self.assertEqual(self.client.post(reverse('car_booking_cancel', args=[booking_id])).status_code, 403)
        self.client.force_login(self.sales)
        self.assertEqual(self.client.post(reverse('car_booking_cancel', args=[booking_id])).status_code, 200)
        self.assertFalse(Booking.objects.exists())

    def test_notifications_bell(self):
        self.book(self.sales)
        self.client.force_login(self.marketing)
        data = self.client.get(reverse('notifications')).json()
        self.assertEqual(data['unread'], 1)
        self.client.post(reverse('notifications_read'))
        self.assertEqual(self.client.get(reverse('notifications')).json()['unread'], 0)

    @override_settings(OFFICE365={'TENANT_ID': 't', 'CLIENT_ID': 'c', 'CLIENT_SECRET': 's', 'SENDER': 'cars@example.com'})
    def test_email_goes_to_the_rest_of_the_team(self):
        with mock.patch('fe_orders.office365._send_later') as send:
            self.book(self.sales)
        to = send.call_args.args[4]
        self.assertEqual(to, ['mele@example.com'])

    @override_settings(OFFICE365={'TENANT_ID': 't', 'CLIENT_ID': 'c', 'CLIENT_SECRET': 's', 'SENDER': 'cars@example.com'})
    def test_email_comes_from_booker_to_every_group_but_fe_boys(self):
        fe = User.objects.create_user('semo', email='semo@example.com', password='x')
        fe.groups.add(Group.objects.get_or_create(name='fe_boys')[0])
        boss = User.objects.create_user('boss', email='boss@example.com', password='x')
        boss.groups.add(Group.objects.get_or_create(name='Manager')[0])
        other = User.objects.create_user('lisi', email='lisi@example.com', password='x')
        other.groups.add(Group.objects.get_or_create(name='Accounts')[0])   # any group but fe_boys
        User.objects.create_user('nogroup', email='nogroup@example.com', password='x')
        with mock.patch('fe_orders.office365._send_later') as send:
            self.book(self.marketing)
        self.assertEqual(send.call_args.args[4], ['boss@example.com', 'lisi@example.com', 'sione@example.com'])
        self.assertEqual(send.call_args.kwargs['sender'], 'mele@example.com')

    @override_settings(OFFICE365={'TENANT_ID': 't', 'CLIENT_ID': 'c', 'CLIENT_SECRET': 's', 'SENDER': 'cars@example.com'})
    def test_falls_back_to_shared_mailbox_when_booker_cannot_send(self):
        from fe_orders import office365
        senders = []

        def fake_send(to, subject, body, sender=None):
            senders.append(sender)
            if sender:
                raise office365.Office365Error('HTTP 404: mailbox not found')
        # the thread runs inline, so the patches must still be in place when the commit callbacks run
        with mock.patch('fe_orders.office365.send_mail', fake_send), \
                mock.patch('threading.Thread', lambda target, daemon: mock.Mock(start=target)), \
                self.captureOnCommitCallbacks(execute=True):
            self.book(self.sales)
        self.assertEqual(senders, ['sione@example.com', None])
        self.assertTrue(Booking.objects.get().email_status.startswith('Sent from cars@example.com'))

    def test_same_car_same_day_different_times(self):
        self.assertEqual(self.book(self.sales, start=self.start, hours=2).status_code, 200)               # 09:00-11:00
        self.assertEqual(self.book(self.marketing, start=self.start + timedelta(hours=3)).status_code, 200)  # 12:00-14:00
        self.assertEqual(self.book(self.sales, start=self.start + timedelta(hours=6)).status_code, 200)     # 15:00-17:00
        self.assertEqual(Booking.objects.filter(car='81').count(), 3)

    def edit(self, user, booking_id, start, hours=2, car='81', reason='Changed'):
        self.client.force_login(user)
        return self.client.post(reverse('car_booking_edit', args=[booking_id]), {
            'car': car, 'start': _fmt(start), 'end': _fmt(start + timedelta(hours=hours)), 'reason': reason})

    def test_owner_can_edit_own_booking(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        r = self.edit(self.sales, booking_id, self.start + timedelta(hours=1), reason='Later start')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Booking.objects.get().reason, 'Later start')
        self.assertTrue(Notification.objects.filter(recipient=self.marketing, message__contains='changed their booking').exists())

    def test_cannot_edit_or_cancel_someone_elses_booking(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        self.assertEqual(self.edit(self.marketing, booking_id, self.start).status_code, 403)
        self.assertEqual(self.client.post(reverse('car_booking_cancel', args=[booking_id])).status_code, 403)
        self.assertEqual(Booking.objects.get().reason, 'Shop visits')
        booking = self.client.get(reverse('car_booking_search'), {'q': 'shop'}).json()['bookings'][0]
        self.assertFalse(booking['can_change'])   # so the page shows a lock instead of Edit / Cancel

    def test_manager_and_admin_can_edit_anyones_booking(self):
        manager = User.objects.create_user('boss', password='x')
        manager.groups.add(Group.objects.get_or_create(name='Manager')[0])
        admin = User.objects.create_superuser('root', password='x')
        booking_id = self.book(self.sales).json()['booking']['id']
        self.assertEqual(self.edit(manager, booking_id, self.start, car='Ringo').status_code, 200)
        self.assertTrue(Notification.objects.filter(recipient=self.sales, message__contains='(Manager) changed your booking').exists())
        self.assertEqual(self.edit(admin, booking_id, self.start, car='82').status_code, 200)
        self.assertEqual(Booking.objects.get().car, '82')

    def test_edit_cannot_create_a_clash(self):
        self.book(self.marketing, start=self.start + timedelta(hours=3))           # 12:00-14:00
        mine = self.book(self.sales).json()['booking']['id']                        # 09:00-11:00
        self.assertEqual(self.edit(self.sales, mine, self.start + timedelta(hours=2)).status_code, 409)   # 11:00-13:00 overlaps
        self.assertEqual(self.edit(self.sales, mine, self.start, hours=3).status_code, 200)              # 09:00-12:00 just touches

    @override_settings(OFFICE365={'TENANT_ID': 't', 'CLIENT_ID': 'c', 'CLIENT_SECRET': 's', 'SENDER': 'cars@example.com'},
                       SITE_URL='http://10.10.8.49:8000')
    def test_email_button_opens_the_office_server(self):
        with mock.patch('fe_orders.office365._send_later') as send:
            self.book(self.sales)
        body = send.call_args.args[3]
        self.assertIn('href="http://10.10.8.49:8000/car-allocations/?car=81&amp;date=', body)


@override_settings(OFFICE365={})
class BookingApprovalTests(TestCase):
    def setUp(self):
        self.sales = User.objects.create_user('sione', first_name='Sione', email='sione@example.com', password='x')
        self.sales.groups.add(Group.objects.get_or_create(name='Sales')[0])
        self.marketing = User.objects.create_user('mele', email='mele@example.com', password='x')
        self.marketing.groups.add(Group.objects.get_or_create(name='Marketing')[0])
        self.manager = User.objects.create_user('boss', first_name='Boss', email='boss@example.com', password='x')
        self.manager.groups.add(Group.objects.get_or_create(name='Manager')[0])
        self.start = (timezone.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    def book(self, user, car='81', start=None, hours=2):
        self.client.force_login(user)
        start = start or self.start
        return self.client.post(reverse('car_book'), {
            'car': car, 'start': _fmt(start), 'end': _fmt(start + timedelta(hours=hours)), 'reason': 'Shop visits'})

    def decide(self, user, booking_id, decision, comment=''):
        self.client.force_login(user)
        return self.client.post(reverse(f'car_booking_{decision}', args=[booking_id]), {'comment': comment})

    def test_staff_booking_waits_and_managers_are_asked(self):
        r = self.book(self.sales)
        self.assertEqual(r.json()['booking']['status'], 'pending')
        self.assertTrue(Notification.objects.filter(recipient=self.manager, message__startswith='Approval needed').exists())
        self.assertFalse(Notification.objects.filter(recipient=self.marketing, message__startswith='Approval needed').exists())

    def test_managers_own_booking_is_approved(self):
        self.assertEqual(self.book(self.manager).json()['booking']['status'], 'approved')

    def test_only_a_manager_can_decide(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        self.assertEqual(self.decide(self.marketing, booking_id, 'approve').status_code, 403)
        self.assertEqual(self.decide(self.sales, booking_id, 'decline', 'no').status_code, 403)
        self.assertEqual(Booking.objects.get().status, 'pending')

    def test_manager_sees_the_waiting_list_staff_do_not(self):
        self.book(self.sales)
        self.client.force_login(self.manager)
        self.assertEqual(len(self.client.get(reverse('car_bookings')).json()['pending']), 1)
        self.assertContains(self.client.get(reverse('car_allocations')), 'Waiting for your approval')
        self.client.force_login(self.marketing)
        self.assertNotIn('pending', self.client.get(reverse('car_bookings')).json())
        self.assertNotContains(self.client.get(reverse('car_allocations')), 'Waiting for your approval')

    def test_approve_notifies_the_booker(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        self.assertEqual(self.decide(self.manager, booking_id, 'approve').status_code, 200)
        b = Booking.objects.get()
        self.assertEqual((b.status, b.decided_by), ('approved', self.manager))
        self.assertTrue(Notification.objects.filter(recipient=self.sales, message__startswith='Boss approved your 81 booking').exists())

    def test_decline_needs_a_comment_and_sends_it_to_the_booker(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        self.assertEqual(self.decide(self.manager, booking_id, 'decline', '  ').status_code, 400)
        self.assertEqual(self.decide(self.manager, booking_id, 'decline', 'Car is needed for Savaii').status_code, 200)
        b = Booking.objects.get()
        self.assertEqual((b.status, b.decline_reason), ('declined', 'Car is needed for Savaii'))
        n = Notification.objects.get(recipient=self.sales, message__contains='declined')
        self.assertIn('Car is needed for Savaii', n.message)

    def test_declined_booking_frees_the_slot_and_is_hidden_from_others(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        self.assertEqual(self.book(self.marketing).status_code, 409)   # pending holds the car
        self.decide(self.manager, booking_id, 'decline', 'No')
        self.client.force_login(self.sales)
        self.assertEqual(self.client.get(reverse('car_bookings'), {'start': self.start.date().isoformat()}).json()['bookings'][0]['decline_reason'], 'No')
        self.client.force_login(self.marketing)
        self.assertEqual(self.client.get(reverse('car_bookings'), {'start': self.start.date().isoformat()}).json()['bookings'], [])
        self.assertEqual(self.book(self.marketing).status_code, 200)
        # the old booking can't be approved back over the new one
        self.assertEqual(self.decide(self.manager, booking_id, 'approve').status_code, 409)

    def test_staff_moving_an_approved_booking_needs_approval_again(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        self.decide(self.manager, booking_id, 'approve')
        self.client.force_login(self.sales)
        self.client.post(reverse('car_booking_edit', args=[booking_id]), {
            'car': '81', 'start': _fmt(self.start + timedelta(hours=1)), 'end': _fmt(self.start + timedelta(hours=3)), 'reason': 'Later'})
        self.assertEqual(Booking.objects.get().status, 'pending')

    @override_settings(OFFICE365={'TENANT_ID': 't', 'CLIENT_ID': 'c', 'CLIENT_SECRET': 's', 'SENDER': 'cars@example.com'})
    def test_decision_is_emailed_to_the_booker(self):
        booking_id = self.book(self.sales).json()['booking']['id']
        with mock.patch('fe_orders.office365._send_later') as send:
            self.decide(self.manager, booking_id, 'decline', 'Car is in for service')
        self.assertEqual(send.call_args.args[4], ['sione@example.com'])
        self.assertIn('declined', send.call_args.args[2])
        self.assertIn('Car is in for service', send.call_args.args[3])


@override_settings(OFFICE365={})
class FinanceTests(TestCase):
    """Financial Controller and Finance Staff: their own dashboard, a read-only Atlas, and the Finance cars."""
    def setUp(self):
        def user(name, group):
            u = User.objects.create_user(name, first_name=name.capitalize(), email=f'{name}@example.com', password='x')
            u.groups.add(Group.objects.get_or_create(name=group)[0])
            return u
        self.staff = user('lagi', 'Finance Staff')
        self.fin_manager = user('tina', 'Financial Controller')
        self.sales = user('sione', 'Sales')
        self.manager = user('boss', 'Manager')
        self.start = (timezone.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    def book(self, user, car='Raize 18', hours=2):
        self.client.force_login(user)
        return self.client.post(reverse('car_book'), {
            'car': car, 'start': _fmt(self.start), 'end': _fmt(self.start + timedelta(hours=hours)), 'reason': 'Bank run'})

    def decide(self, user, booking_id, decision='approve', comment=''):
        self.client.force_login(user)
        return self.client.post(reverse(f'car_booking_{decision}', args=[booking_id]), {'comment': comment})

    def test_finance_get_the_finance_dashboard(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Finance Dashboard')
        self.assertContains(r, 'Raize 17')
        self.assertContains(r, 'Finance Staff')
        self.assertNotContains(r, 'All Clients')
        self.client.force_login(self.fin_manager)
        self.assertContains(self.client.get(reverse('dashboard')), 'Waiting for your approval')

    def test_finance_only_open_dashboard_atlas_and_cars(self):
        self.client.force_login(self.staff)
        for name in ('shop_list', 'corporate_sales', 'promotion_list', 'reports', 'fe_order_list'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get('/admin/').status_code, 403)
        for name in ('atlas', 'car_allocations', 'notifications'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_atlas_is_read_only(self):
        self.client.force_login(self.fin_manager)
        r = self.client.get(reverse('atlas'))
        self.assertTrue(r.context['atlas_data']['read_only'])
        r = self.client.post(reverse('atlas_shop_location', args=[1]), '{"reset": true}', content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_finance_book_only_the_finance_cars(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse('car_allocations'))
        self.assertEqual(r.context['cars'], ['Raize 18', 'Raize 17'])
        self.assertContains(r, 'A Financial Controller approves each booking')
        self.assertEqual(self.book(self.staff, car='81').status_code, 400)
        self.assertEqual(self.book(self.sales, car='Raize 18').status_code, 400)
        self.assertEqual(self.book(self.staff).json()['booking']['status'], 'pending')

    def test_finance_manager_approves_finance_cars_only(self):
        raize = self.book(self.staff).json()['booking']['id']
        office = self.book(self.sales, car='81').json()['booking']['id']
        self.assertEqual(self.decide(self.staff, raize).status_code, 403)
        self.assertEqual(self.decide(self.manager, raize).status_code, 403)
        self.assertEqual(self.decide(self.fin_manager, office).status_code, 403)
        self.assertEqual(self.decide(self.fin_manager, raize).status_code, 200)
        self.assertEqual(Booking.objects.get(pk=raize).status, 'approved')
        self.assertEqual(Booking.objects.get(pk=office).status, 'pending')
        self.assertTrue(Notification.objects.filter(recipient=self.staff, message__startswith='Tina approved your Raize 18').exists())

    def test_finance_managers_own_booking_is_approved(self):
        self.assertEqual(self.book(self.fin_manager).json()['booking']['status'], 'approved')

    def test_each_team_sees_only_its_own_cars(self):
        self.book(self.staff)
        self.book(self.sales, car='81')
        day = {'start': self.start.date().isoformat()}
        self.client.force_login(self.fin_manager)
        data = self.client.get(reverse('car_bookings'), day).json()
        self.assertEqual([b['car'] for b in data['bookings']], ['Raize 18'])
        self.assertEqual([b['car'] for b in data['pending']], ['Raize 18'])
        self.assertEqual(sorted(data['status']), ['Raize 17', 'Raize 18'])
        self.client.force_login(self.manager)
        data = self.client.get(reverse('car_bookings'), day).json()
        self.assertEqual([b['car'] for b in data['bookings']], ['81'])
        self.assertEqual([b['car'] for b in data['pending']], ['81'])

    def test_notices_stay_within_each_team(self):
        self.book(self.staff)
        self.assertTrue(Notification.objects.filter(recipient=self.fin_manager, message__startswith='Approval needed').exists())
        self.assertFalse(Notification.objects.filter(recipient__in=[self.sales, self.manager]).exists())
        Notification.objects.all().delete()
        self.book(self.sales, car='81')
        self.assertFalse(Notification.objects.filter(recipient__in=[self.staff, self.fin_manager]).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.manager, message__startswith='Approval needed').exists())

    def test_email_recipients_follow_the_car(self):
        from . import notify
        self.assertEqual(notify.car_recipients('Raize 18', self.staff), ['tina@example.com'])
        self.assertEqual(notify.car_recipients('81', self.sales), ['boss@example.com'])

    def test_admins_cannot_see_book_or_approve_finance_cars(self):
        admin = User.objects.create_superuser('admin', 'admin@example.com', 'x')
        raize = self.book(self.staff).json()['booking']['id']
        self.assertFalse(Notification.objects.filter(recipient=admin).exists())
        self.assertEqual(self.decide(admin, raize).status_code, 403)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse('car_allocations')).context['cars'], ['81', '82', 'Ringo', 'Ranger'])
        data = self.client.get(reverse('car_bookings'), {'start': self.start.date().isoformat()}).json()
        self.assertEqual((data['bookings'], data['pending']), ([], []))
        self.assertEqual(self.book(admin).status_code, 400)
        self.assertEqual(notify_recipients('Raize 18', self.staff), ['tina@example.com'])

    def test_only_the_financial_controller_hears_about_finance_bookings(self):
        other = User.objects.create_user('ana', email='ana@example.com', password='x')
        other.groups.add(Group.objects.get(name='Finance Staff'))
        self.book(self.staff)
        self.assertEqual(list(Notification.objects.values_list('recipient__username', flat=True)), ['tina'])
