import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from shops.models import Shop

from .gazetteer import locate
from .models import ShopLocation


class GazetteerTests(TestCase):
    def test_matches_messy_addresses(self):
        self.assertEqual(locate('POUTASI  FALEALILI'), locate('POUTASI'))
        self.assertEqual(locate("MOTO'OTUA"), locate('MOTOOTUA'))
        self.assertEqual(locate('Vaitele-Uta'), locate('VAITELE UTA'))
        self.assertNotEqual(locate('MATAUTU FALEALILI'), locate('MATAUTU'))

    def test_unknown_address(self):
        self.assertIsNone(locate('n/a'))
        self.assertIsNone(locate(None))


class AtlasViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff', password='pw')
        self.client.login(username='staff', password='pw')
        self.shop = Shop.objects.create(name='Jane Store', address='LALOVAEA', territory='EC2')
        self.lost = Shop.objects.create(name='Lost Store', address='n/a')

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('atlas')).status_code, 302)

    def test_page_lists_shops(self):
        data = self.client.get(reverse('atlas')).context['atlas_data']
        by_name = {s['name']: s for s in data['shops']}
        self.assertIsNotNone(by_name['Jane Store']['lat'])
        self.assertIsNone(by_name['Lost Store']['lat'])
        self.assertEqual(by_name['Lost Store']['territory'], 'Unassigned')
        self.assertIn('Unassigned', data['territories'])

    def _post(self, shop, body):
        return self.client.post(reverse('atlas_shop_location', args=[shop.id]),
                                json.dumps(body), content_type='application/json')

    def test_pin_and_reset(self):
        r = self._post(self.lost, {'lat': -13.84, 'lng': -171.77})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['manual'])
        self.assertEqual(ShopLocation.objects.get(shop=self.lost).updated_by, 'staff')

        r = self._post(self.lost, {'reset': True})
        self.assertIsNone(r.json()['lat'])
        self.assertFalse(ShopLocation.objects.exists())

    def test_rejects_points_outside_samoa(self):
        r = self._post(self.shop, {'lat': -36.8, 'lng': 174.7})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ShopLocation.objects.exists())
