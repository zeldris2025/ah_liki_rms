from datetime import date, timedelta

from django.core.management.base import BaseCommand

from shops.models import Promotion


def _d(days):
    return date.today() + timedelta(days=days)


# (company, name, start offset, end offset, details, prizes)
DEMO_PROMOTIONS = [
    ('Ah Liki Wholesale', 'Bulk Rice Saver', -20, 25,
     '10% off all 25kg rice bags for registered retail shops.\n'
     'Minimum order of 10 bags per delivery. Discount applied at invoicing.', ''),
    ('Ah Liki Wholesale', 'Christmas Hamper Bundle', 45, 90,
     'Pre-packed festive hampers (tinned fish, corned beef, biscuits and soft drinks) '
     'at a special wholesale price for shops reselling to families over the holiday season.', ''),
    ('Ah Liki Wholesale', 'Top Retailer Rewards', -60, 95,
     'Shops that reach WST 5,000 in monthly purchases earn a 2% rebate credited to their next order.', '2% rebate on next order for every shop over WST 5,000 a month'),
    ('Ah Liki Wholesale', 'Winter Noodle Clearance', -120, -40,
     'Buy 5 cartons of instant noodles and get 15% off. Promotion has now closed.', ''),

    ('Farmer Joe', 'Weekend Fresh Produce Deal', -10, 30,
     '20% off selected local fruit and vegetables every Saturday and Sunday.', ''),
    ('Farmer Joe', 'Buy 2 Get 1 Free Frozen Chicken', -5, 21,
     'Buy two 10lb frozen chicken packs and get a third free. Limit of 3 free packs per customer.', ''),
    ('Farmer Joe', 'Back to School Giveaway', -75, -45,
     'Free stationery pack with every WST 150 spend on groceries. While stocks lasted.', 'Free stationery pack with every WST 150 spend'),

    ('Taula', 'Taula Fridge Placement Drive', -30, 60,
     'Qualifying shops receive a branded Taula fridge on loan when they commit to a monthly '
     'minimum order of 20 cases.', ''),
    ('Taula', 'Teuila Festival Competition', 14, 35,
     'Customers who buy a 6-pack go into a draw to win festival VIP passes and Taula merchandise. '
     'Entry forms supplied to participating outlets.', '1st — 2 festival VIP passes + Taula merchandise pack\n2nd — Taula merchandise pack\n3rd — 24-pack of Taula'),
    ('Taula', 'Summer 24-Pack Special', -15, 45,
     'Discounted 24-pack cases for HORECCA clients. Paused while stock is replenished.', ''),

    ('Burger Bills', 'Family Combo Tuesday', -40, 50,
     'Two burgers, two kids meals, large fries and 4 drinks for one fixed price every Tuesday.', ''),
    ('Burger Bills', 'Free Upsize Friday', -7, 28,
     'Free upsize on any combo meal ordered on Fridays.', ''),
    ('Burger Bills', 'Burger Bills Stamp Card', 7, 120,
     'Collect a stamp with every burger purchase. The 10th burger is free.', 'Free burger on the 10th stamp'),
]


class Command(BaseCommand):
    help = 'Populate the database with mock promotions for each partner company'

    def handle(self, *args, **options):
        created = 0
        for company, name, start, end, details, prizes in DEMO_PROMOTIONS:
            _, was_created = Promotion.objects.get_or_create(
                company=company, name=name,
                defaults={
                    'start_date': _d(start),
                    'end_date': _d(end),
                    'details': details,
                    'prizes': prizes,
                },
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f'✅ Promotions: {created} created, {len(DEMO_PROMOTIONS) - created} already existed'))
