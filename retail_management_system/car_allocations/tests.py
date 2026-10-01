from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Booking, Notification


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
