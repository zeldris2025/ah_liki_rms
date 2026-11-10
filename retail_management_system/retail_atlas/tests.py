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
        from django.contrib.auth.models import Group
        self.user = User.objects.create_user('staff', password='pw')
        self.user.groups.add(Group.objects.get(name='Sales'))   # staff with no access level can't move pins
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


class CompanyLocationTests(TestCase):
    """Our companies' sites: added and moved in the admin (map picker), shown as their own layer on the atlas."""
    def setUp(self):
        from .models import CompanyLocation
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'pw')
        self.site = CompanyLocation.objects.create(company='Farmer Joe', name='Farmer Joe Vaitele', kind='supermarket',
                                                   latitude='-13.8270', longitude='-171.8020')
        CompanyLocation.objects.create(company='Farmer Joe', name='Old store', latitude='-13.83', longitude='-171.76',
                                       is_published=False)

    def test_atlas_shows_published_sites_with_edit_link_for_admins(self):
        self.client.force_login(self.admin)
        companies = self.client.get(reverse('atlas')).context['atlas_data']['companies']
        self.assertEqual([c['name'] for c in companies], ['Farmer Joe Vaitele'])
        self.assertEqual(companies[0]['kind'], 'Supermarket')
        self.assertIn(f'/admin/retail_atlas/companylocation/{self.site.id}/change/', companies[0]['edit_url'])
        staff = User.objects.create_user('staff', password='pw')
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('atlas')).context['atlas_data']['companies'][0]['edit_url'], '')

    def test_admin_pages_have_the_map_picker(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('admin:retail_atlas_companylocation_add'))
        self.assertContains(r, 'id="location-map"')
        self.assertContains(r, 'leaflet.js')
        self.assertContains(r, '<option value="Farmer Joe">')   # company suggestions
        r = self.client.get(reverse('admin:retail_atlas_companylocation_change', args=[self.site.id]))
        self.assertContains(r, 'id="location-map"')
        self.assertContains(self.client.get(reverse('admin:retail_atlas_shoplocation_add')), 'id="location-map"')

    def test_admin_adds_a_site_and_rejects_points_outside_samoa(self):
        from .models import CompanyLocation
        self.client.force_login(self.admin)
        data = {'company': 'Burger Bills', 'name': 'Burger Bills Apia', 'kind': 'restaurant', 'is_published': 'on',
                'address': 'Apia', 'phone': '', 'notes': '', 'latitude': '-13.833', 'longitude': '-171.766'}
        r = self.client.post(reverse('admin:retail_atlas_companylocation_add'), data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(CompanyLocation.objects.get(name='Burger Bills Apia').updated_by, 'boss')
        r = self.client.post(reverse('admin:retail_atlas_companylocation_add'), {**data, 'name': 'Far away', 'latitude': '-36.85', 'longitude': '174.76'})
        self.assertContains(r, 'outside Samoa')
        self.assertFalse(CompanyLocation.objects.filter(name='Far away').exists())

    def test_admin_pins_a_client_shop(self):
        shop = Shop.objects.create(name='Jane Store', address='n/a')
        self.client.force_login(self.admin)
        r = self.client.post(reverse('admin:retail_atlas_shoplocation_add'),
                             {'shop': shop.id, 'latitude': '-13.84', 'longitude': '-171.75'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ShopLocation.objects.get(shop=shop).updated_by, 'boss')
        by_name = {s['name']: s for s in self.client.get(reverse('atlas')).context['atlas_data']['shops']}
        self.assertTrue(by_name['Jane Store']['manual'])
