import datetime
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from car_allocations.models import Notification

from .models import SocialCount, last_update_day, next_update_day, office_today


def user(name, *groups, **extra):
    u = User.objects.create_user(name, first_name=name.capitalize(), email=f'{name}@example.com', password='x', **extra)
    for g in groups:
        u.groups.add(Group.objects.get_or_create(name=g)[0])
    return u


def last_week(weekday):
    """A day of last week (0 = Monday, 5 = Saturday), so it's always in the past."""
    today = office_today()
    return today - timedelta(days=today.weekday() + 7) + timedelta(days=weekday)


def boxes(day, **numbers):
    """The update form's POST data: numbers like farmer_joe_facebook=120."""
    return {'date': day.isoformat(), **{k: str(v) for k, v in numbers.items()}}


class UpdateDayTests(TestCase):
    def test_update_days_are_mondays_and_saturdays(self):
        monday, saturday = datetime.date(2026, 10, 26), datetime.date(2026, 10, 31)
        self.assertEqual(last_update_day(monday), monday)
        self.assertEqual(last_update_day(datetime.date(2026, 10, 30)), monday)    # Friday
        self.assertEqual(last_update_day(datetime.date(2026, 11, 1)), saturday)   # Sunday
        self.assertEqual(next_update_day(monday), saturday)
        self.assertEqual(next_update_day(saturday), datetime.date(2026, 11, 2))


@override_settings(OFFICE365={})
class SocialAccessTests(TestCase):
    """The Social group: their own dashboard, Social #s and analytics, a read-only Atlas and the office cars."""
    def setUp(self):
        self.social = user('ana', 'Social')
        self.manager = user('boss', 'Manager')
        self.sales = user('sione', 'Sales')
        self.marketing = user('mele', 'Marketing')

    def test_the_group_exists(self):
        self.assertTrue(Group.objects.filter(name='Social').exists())

    def test_social_get_the_social_dashboard_and_menu(self):
        self.client.force_login(self.social)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Social Dashboard')
        self.assertContains(r, 'Sales and Marketing')   # still the SMS
        for tab in ('Dashboard', 'Analytics', 'Ah Liki Atlas', 'Social #s', 'Car Allocations'):
            self.assertContains(r, tab)
        self.assertContains(r, reverse('social_analytics'))
        self.assertNotContains(r, 'All Clients')
        self.assertNotContains(r, 'Corporate Sales')
        self.assertEqual(r.context['user_role'], 'Social')

    def test_social_only_open_their_pages(self):
        self.client.force_login(self.social)
        for name in ('social_numbers', 'social_update', 'social_analytics', 'atlas', 'car_allocations', 'notifications'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for name in ('shop_list', 'analytics', 'corporate_sales', 'promotion_list', 'sponsorship_list', 'reports',
                     'monthly_sales', 'fe_order_list', 'hr_vacancies'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get('/admin/').status_code, 403)

    def test_atlas_is_read_only(self):
        self.client.force_login(self.social)
        self.assertTrue(self.client.get(reverse('atlas')).context['atlas_data']['read_only'])
        r = self.client.post(reverse('atlas_shop_location', args=[1]), '{"reset": true}', content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_managers_also_get_social_numbers_but_not_sales_or_marketing(self):
        self.client.force_login(self.manager)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, reverse('social_numbers'))
        self.assertNotContains(r, 'Social Dashboard')
        self.assertEqual(self.client.get(reverse('social_numbers')).status_code, 200)
        self.assertEqual(self.client.get(reverse('social_analytics')).status_code, 200)
        for u in (self.sales, self.marketing):
            self.client.force_login(u)
            self.assertNotContains(self.client.get(reverse('dashboard')), reverse('social_numbers'))
            self.assertEqual(self.client.get(reverse('social_numbers')).status_code, 403)

    def test_another_level_wins_over_social(self):
        both = user('lisa', 'Social', 'Marketing')
        self.client.force_login(both)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Social Dashboard')
        self.assertEqual(self.client.get(reverse('shop_list')).status_code, 200)

    def test_social_book_the_office_cars_and_hear_about_bookings(self):
        self.client.force_login(self.social)
        r = self.client.get(reverse('car_allocations'))
        self.assertEqual(r.context['cars'], ['81', '82', 'Ringo', 'Ranger'])
        start = (timezone.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        fmt = lambda dt: timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')
        self.client.force_login(self.sales)
        self.client.post(reverse('car_book'), {'car': '81', 'start': fmt(start), 'end': fmt(start + timedelta(hours=2)),
                                               'reason': 'Deliveries'})
        self.assertTrue(Notification.objects.filter(recipient=self.social).exists())


class SocialNumbersTests(TestCase):
    def setUp(self):
        self.social = user('ana', 'Social')
        self.client.force_login(self.social)
        self.monday = last_week(0)

    def test_update_saves_every_company_for_the_day(self):
        r = self.client.post(reverse('social_update'), boxes(
            self.monday, ah_liki_wholesale_facebook=5200, ah_liki_wholesale_instagram=1800,
            farmer_joe_facebook=3100, ink_pro_instagram=640))
        self.assertRedirects(r, reverse('social_numbers'))
        self.assertEqual(SocialCount.objects.filter(date=self.monday).count(), 3)
        ink = SocialCount.objects.get(company='ink_pro')
        self.assertEqual((ink.facebook, ink.instagram, ink.updated_by), (None, 640, self.social))

    def test_saving_again_corrects_and_clearing_removes(self):
        self.client.post(reverse('social_update'), boxes(self.monday, farmer_joe_facebook=3100, burger_bills_facebook=900))
        self.client.post(reverse('social_update'), boxes(self.monday, farmer_joe_facebook=3150))
        self.assertEqual(SocialCount.objects.get(company='farmer_joe').facebook, 3150)
        self.assertFalse(SocialCount.objects.filter(company='burger_bills').exists())

    def test_only_mondays_and_saturdays_in_the_past(self):
        r = self.client.post(reverse('social_update'), boxes(last_week(1), farmer_joe_facebook=1))
        self.assertContains(r, 'Tuesday isn’t an update day')
        future = next_update_day(office_today() + timedelta(days=7))
        r = self.client.post(reverse('social_update'), boxes(future, farmer_joe_facebook=1))
        self.assertContains(r, 'That day hasn’t come yet')
        r = self.client.post(reverse('social_update'), boxes(self.monday, farmer_joe_facebook=-4))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(SocialCount.objects.exists())

    def test_the_form_loads_the_days_saved_numbers(self):
        SocialCount.objects.create(company='farmer_joe', date=self.monday, facebook=3100)
        r = self.client.get(reverse('social_update') + f'?date={self.monday:%Y-%m-%d}')
        self.assertContains(r, 'value="3100"')
        self.assertContains(r, 'Edit numbers')

    def test_table_shows_date_facebook_instagram_and_change(self):
        SocialCount.objects.create(company='farmer_joe', date=self.monday - timedelta(days=2), facebook=3000, instagram=500)
        SocialCount.objects.create(company='farmer_joe', date=self.monday, facebook=3100, instagram=480)
        r = self.client.get(reverse('social_numbers') + '?company=farmer_joe')
        self.assertContains(r, '3,100')
        self.assertContains(r, '+100')
        self.assertContains(r, '−20')
        self.assertNotContains(self.client.get(reverse('social_numbers')), '3,100')   # Ah Liki Wholesale's tab

    def test_status_lists_the_companies_still_to_update(self):
        day = last_update_day()
        SocialCount.objects.create(company='farmer_joe', date=day, facebook=1)
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.context['status']['done'], 1)
        self.assertIn('Ink Pro', r.context['status']['missing'])
        self.assertNotIn('Farmer Joe', r.context['status']['missing'])

    def test_analytics_charts_and_growth(self):
        self.assertContains(self.client.get(reverse('social_analytics')), 'No social numbers yet')
        SocialCount.objects.create(company='ink_pro', date=self.monday - timedelta(days=30), facebook=1000, instagram=200)
        SocialCount.objects.create(company='ink_pro', date=self.monday, facebook=1250, instagram=260)
        r = self.client.get(reverse('social_analytics') + '?range=90')
        ink = next(c for c in r.context['charts'] if c['key'] == 'ink_pro')
        self.assertEqual(ink['facebook'], [1000, 1250])
        row = next(s for s in r.context['summary'] if s['key'] == 'ink_pro')
        self.assertEqual(row['platforms'][0]['since'], {'n': 250, 'pct': 25.0})
        self.assertEqual(r.context['totals'][1]['value'], 260)
        self.assertContains(r, 'id="social-charts"')


class SocialImportTests(TestCase):
    def setUp(self):
        self.social = user('ana', 'Social')
        self.client.force_login(self.social)
        self.monday, self.saturday = last_week(0), last_week(5)

    def upload(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(reverse('social_import'),
                                {'csv_file': SimpleUploadedFile('social.csv', text.encode('utf-8'), 'text/csv')})

    def test_import_adds_updates_and_skips(self):
        SocialCount.objects.create(company='farmer_joe', date=self.monday, facebook=3000, instagram=400)
        r = self.upload(
            'Date,Company,Facebook,Instagram\n'
            f'{self.monday:%Y-%m-%d},Ah Liki Wholesale,"5,200",1800\n'
            f'{self.monday:%d/%m/%Y},farmer joe,3100,\n'          # updates Facebook, keeps Instagram
            f'{self.saturday:%Y-%m-%d},Ink Pro,640,210\n'
            f'{self.monday:%Y-%m-%d},Coca Cola,1,1\n'
            f'{last_week(2):%Y-%m-%d},Burger Bills,1,1\n'           # a Wednesday
            f'{self.monday:%Y-%m-%d},NSW,lots,\n')
        result = r.context['result']
        self.assertEqual((result['created'], result['updated'], len(result['skipped'])), (2, 1, 3))
        joe = SocialCount.objects.get(company='farmer_joe')
        self.assertEqual((joe.facebook, joe.instagram, joe.updated_by), (3100, 400, self.social))
        self.assertEqual(SocialCount.objects.get(company='ah_liki_wholesale').facebook, 5200)
        self.assertContains(r, 'Coca Cola')
        self.assertContains(r, 'isn’t an update day')
        self.assertContains(r, 'not a whole number')

    def test_reuploading_changes_nothing(self):
        text = f'Date,Company,FB,IG\n{self.monday:%Y-%m-%d},Burger Bills,900,300\n'
        self.upload(text)
        self.assertEqual(self.upload(text).context['result']['unchanged'], 1)
        self.assertEqual(SocialCount.objects.count(), 1)

    def test_file_needs_date_and_company(self):
        self.assertContains(self.upload('Facebook,Instagram\n1,2\n'), 'The file needs a &#x27;Date&#x27; column')

    def test_template_is_for_managers(self):
        self.assertContains(self.client.get(reverse('social_import')), 'Import Social #s')
        self.assertEqual(self.client.get(reverse('social_template')).status_code, 403)
        self.client.force_login(user('boss', 'Manager'))
        r = self.client.get(reverse('social_template'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('Date,Company,Facebook,Instagram', r.content.decode())
        self.assertIn('Natural Samoa Water', r.content.decode())


class SocialPaginationTests(TestCase):
    def test_fifty_updates_per_page(self):
        self.client.force_login(user('ana', 'Social'))
        day = last_week(0)
        for i in range(60):   # 60 Mondays back
            SocialCount.objects.create(company='ink_pro', date=day - timedelta(weeks=i), facebook=1000 + i)
        r = self.client.get(reverse('social_numbers') + '?company=ink_pro')
        self.assertEqual(len(r.context['rows']), 50)
        self.assertContains(r, 'Page 1 of 2')
        self.assertContains(r, '?company=ink_pro&page=2')
        r = self.client.get(reverse('social_numbers') + '?company=ink_pro&page=2')
        self.assertEqual(len(r.context['rows']), 10)
        # the last row on page 1 still shows its change from the first row on page 2
        last = self.client.get(reverse('social_numbers') + '?company=ink_pro').context['rows'][49]
        self.assertEqual(last['platforms'][0]['change']['n'], -1)
