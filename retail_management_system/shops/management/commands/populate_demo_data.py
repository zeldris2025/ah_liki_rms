from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from shops.models import Shop, Business, Sponsorship


class Command(BaseCommand):
    help = 'Populate the database with demo shops, HORECCA businesses, and sponsorships'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Starting demo data population...'))

        # ── Demo Shops ────────────────────────────────────────────────────────

        demo_shops = [
            # Upolu - Region 1
            {
                'name': 'Central Convenience Store',
                'contact_person': 'Tasi Fuafua',
                'phone': '+685 7777 001',
                'address': 'Main Street, Apia',
                'island': 'Upolu',
                'region': 'Region 1',
                'tip_top': True,
            },
            {
                'name': 'Beach Side Market',
                'contact_person': 'Leilani Vaai',
                'phone': '+685 7777 002',
                'address': 'Seaside Rd, Apia',
                'island': 'Upolu',
                'region': 'Region 1',
                'tip_top': False,
            },
            {
                'name': 'Upolu Plaza Shop',
                'contact_person': 'Siale Uili',
                'phone': '+685 7777 003',
                'address': 'Plaza Center, Apia',
                'island': 'Upolu',
                'region': 'Region 1',
                'tip_top': True,
            },
            # Upolu - Region 2
            {
                'name': 'Savai\'i Valley Store',
                'contact_person': 'Fafagaloa Samoa',
                'phone': '+685 7777 004',
                'address': 'Valley Rd, Vailoa',
                'island': 'Upolu',
                'region': 'Region 2',
                'tip_top': False,
            },
            {
                'name': 'Mountain View Retail',
                'contact_person': 'Pepe Toefili',
                'phone': '+685 7777 005',
                'address': 'Highland Ave, Samoa',
                'island': 'Upolu',
                'region': 'Region 2',
                'tip_top': True,
            },
            # Upolu - Region 3
            {
                'name': 'East Side Shops',
                'contact_person': 'Malosi Aileen',
                'phone': '+685 7777 006',
                'address': 'East Way, Samoa',
                'island': 'Upolu',
                'region': 'Region 3',
                'tip_top': False,
            },
            {
                'name': 'Premium Distribution',
                'contact_person': 'Vaovaai Ulafala',
                'phone': '+685 7777 007',
                'address': 'Commerce St, Samoa',
                'island': 'Upolu',
                'region': 'Region 3',
                'tip_top': True,
            },
            # Upolu - Region 4
            {
                'name': 'South Bay Market',
                'contact_person': 'Taulapapa Vai',
                'phone': '+685 7777 008',
                'address': 'Bay Front, Samoa',
                'island': 'Upolu',
                'region': 'Region 4',
                'tip_top': False,
            },
            # Savaii - Region 1
            {
                'name': 'Savaii Main Store',
                'contact_person': 'Fa\'asaleleaga Samoa',
                'phone': '+685 7777 009',
                'address': 'Main Rd, Savaii',
                'island': 'Savaii',
                'region': 'Region 1',
                'tip_top': True,
            },
            {
                'name': 'Island Express Market',
                'contact_person': 'Pule Samoa',
                'phone': '+685 7777 010',
                'address': 'Island Blvd, Savaii',
                'island': 'Savaii',
                'region': 'Region 1',
                'tip_top': False,
            },
            # Savaii - Region 2
            {
                'name': 'Savaii Center Shop',
                'contact_person': 'Tapua\'i Samoa',
                'phone': '+685 7777 011',
                'address': 'Center Sq, Savaii',
                'island': 'Savaii',
                'region': 'Region 2',
                'tip_top': True,
            },
            # Savaii - Region 3
            {
                'name': 'West Savaii Store',
                'contact_person': 'Toaga Laifailai',
                'phone': '+685 7777 012',
                'address': 'West Way, Savaii',
                'island': 'Savaii',
                'region': 'Region 3',
                'tip_top': False,
            },
        ]

        shops_created = 0
        for shop_data in demo_shops:
            shop, created = Shop.objects.get_or_create(
                name=shop_data['name'],
                defaults=shop_data
            )
            if created:
                shops_created += 1
                self.stdout.write(f"  ✓ Created shop: {shop.name}")

        self.stdout.write(self.style.SUCCESS(f'✅ Shops: {shops_created} created'))

        # ── Demo HORECCA Businesses ───────────────────────────────────────────

        demo_businesses = [
            # Upolu
            {
                'name': 'Pacific Islander Hotel',
                'business_type': 'HOTEL',
                'island': 'Upolu',
                'location': 'Apia Beach, Upolu',
            },
            {
                'name': 'Samoa Tradewinds Resort',
                'business_type': 'HOTEL',
                'island': 'Upolu',
                'location': 'Coastal Rd, Apia',
            },
            {
                'name': 'Apia Restaurant & Grill',
                'business_type': 'RESTAURANT',
                'island': 'Upolu',
                'location': 'Central District, Apia',
            },
            {
                'name': 'Island Breeze Café',
                'business_type': 'CAFE',
                'island': 'Upolu',
                'location': 'Main Street, Apia',
            },
            {
                'name': 'Samoan Traditional Eats',
                'business_type': 'RESTAURANT',
                'island': 'Upolu',
                'location': 'Valley Rd, Vailoa',
            },
            {
                'name': 'Fiafia Café & Bar',
                'business_type': 'CAFE',
                'island': 'Upolu',
                'location': 'Entertainment Zone, Apia',
            },
            # Savaii
            {
                'name': 'Savaii Luxury Resort',
                'business_type': 'HOTEL',
                'island': 'Savaii',
                'location': 'Beach Front, Savaii',
            },
            {
                'name': 'Island Fusion Restaurant',
                'business_type': 'RESTAURANT',
                'island': 'Savaii',
                'location': 'Resort District, Savaii',
            },
            {
                'name': 'Lagoon View Hotel',
                'business_type': 'HOTEL',
                'island': 'Savaii',
                'location': 'Lagoon Rd, Savaii',
            },
            {
                'name': 'Coconut Paradise Café',
                'business_type': 'CAFE',
                'island': 'Savaii',
                'location': 'South Bay, Savaii',
            },
            {
                'name': 'Sunset Grill & Bar',
                'business_type': 'RESTAURANT',
                'island': 'Savaii',
                'location': 'Waterfront, Savaii',
            },
        ]

        businesses_created = 0
        for biz_data in demo_businesses:
            biz, created = Business.objects.get_or_create(
                name=biz_data['name'],
                defaults=biz_data
            )
            if created:
                businesses_created += 1
                self.stdout.write(f"  ✓ Created business: {biz.name}")

        self.stdout.write(self.style.SUCCESS(f'✅ HORECCA Clients: {businesses_created} created'))

        # ── Demo Sponsorships ─────────────────────────────────────────────────

        today = date.today()
        demo_sponsorships = [
            {
                'customer': 'Central Convenience Store',
                'type': 'Signage',
                'value': 850.00,
                'status': 'Active',
                'start': today - timedelta(days=90),
                'end': today + timedelta(days=90),
                'notes': 'Large storefront signage with LED lighting',
            },
            {
                'customer': 'Beach Side Market',
                'type': 'Cooler',
                'value': 500.00,
                'status': 'Active',
                'start': today - timedelta(days=60),
                'end': today + timedelta(days=120),
                'notes': 'Branded beverage cooler for promotional display',
            },
            {
                'customer': 'Upolu Plaza Shop',
                'type': 'Vehicle',
                'value': 2500.00,
                'status': 'Active',
                'start': today - timedelta(days=30),
                'end': today + timedelta(days=330),
                'notes': 'Company van wrap with full branding',
            },
            {
                'customer': 'Pacific Islander Hotel',
                'type': 'Event',
                'value': 1200.00,
                'status': 'Active',
                'start': today - timedelta(days=45),
                'end': today + timedelta(days=45),
                'notes': 'Sponsorship of annual Samoa Day celebration',
            },
            {
                'customer': 'Samoa Tradewinds Resort',
                'type': 'Uniform',
                'value': 350.00,
                'status': 'Active',
                'start': today - timedelta(days=15),
                'end': today + timedelta(days=345),
                'notes': 'Staff uniforms with company logo embroidery',
            },
            {
                'customer': 'Apia Restaurant & Grill',
                'type': 'Signage',
                'value': 700.00,
                'status': 'Active',
                'start': today - timedelta(days=75),
                'end': today + timedelta(days=105),
                'notes': 'Interior promotional signage and menu boards',
            },
            {
                'customer': 'Island Breeze Café',
                'type': 'Digital',
                'value': 400.00,
                'status': 'Active',
                'start': today - timedelta(days=10),
                'end': today + timedelta(days=350),
                'notes': 'Digital display screens and social media promotion',
            },
            {
                'customer': 'Savaii Luxury Resort',
                'type': 'Event',
                'value': 3000.00,
                'status': 'Active',
                'start': today - timedelta(days=20),
                'end': today + timedelta(days=40),
                'notes': 'Major sponsor of resort\'s grand reopening gala',
            },
            {
                'customer': 'Samoan Traditional Eats',
                'type': 'Cooler',
                'value': 450.00,
                'status': 'Expired',
                'start': today - timedelta(days=180),
                'end': today - timedelta(days=30),
                'notes': 'Previous cooler placement (expired)',
            },
            {
                'customer': 'Mountain View Retail',
                'type': 'Signage',
                'value': 600.00,
                'status': 'Pending',
                'start': today + timedelta(days=7),
                'end': today + timedelta(days=187),
                'notes': 'Awaiting installation - vinyl storefront wrap',
            },
        ]

        sponsorships_created = 0
        for spon_data in demo_sponsorships:
            spon, created = Sponsorship.objects.get_or_create(
                customer=spon_data['customer'],
                type=spon_data['type'],
                start=spon_data['start'],
                defaults=spon_data
            )
            if created:
                sponsorships_created += 1
                self.stdout.write(f"  ✓ Created sponsorship: {spon.customer} - {spon.type}")

        self.stdout.write(self.style.SUCCESS(f'✅ Sponsorships: {sponsorships_created} created'))

        # ── Summary ───────────────────────────────────────────────────────────

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('✨ Demo data population completed!'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f'  🏪 Shops: {shops_created}')
        self.stdout.write(f'  🏨 HORECCA Clients: {businesses_created}')
        self.stdout.write(f'  🤝 Sponsorships: {sponsorships_created}')
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
