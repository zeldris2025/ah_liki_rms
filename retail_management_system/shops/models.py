import datetime
import re

from django.db import models


# ── Retail Shops ──────────────────────────────────────────────────────────────

class Shop(models.Model):
    ISLAND_CHOICES = [
        ('Upolu',  'Upolu'),
        ('Savaii', 'Savaii'),
    ]
    TERRITORY_CHOICES = [
        ('EC1', 'EC1'),
        ('EC2', 'EC2'),
        ('EC3', 'EC3'),
        ('LFG', 'LFG'),
        ('VT1', 'VT1'),
        ('VT2', 'VT2'),
        ('VT3', 'VT3'),
        ('WC1', 'WC1'),
        ('WC2', 'WC2'),
        ('WC4', 'WC4'),
        ('TWN', 'TWN'),
        ('TWN1', 'TWN1'),
        ('TW1', 'TW1'),
    ]

    # Customer code from the office system; the key the CSV uploads match on.
    # Older clients may not have one yet; they get it on their first upload (matched by name).
    customer_code  = models.CharField(max_length=50, unique=True, null=True, blank=True)
    name           = models.CharField(max_length=255)
    customer_type  = models.CharField(max_length=100, blank=True, default='', help_text='e.g. Retail, Wholesale, Hotel')
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    address        = models.CharField(max_length=255, blank=True, null=True, default='n/a')
    island         = models.CharField(max_length=50,  choices=ISLAND_CHOICES, default='Upolu')
    phone          = models.CharField(max_length=50,  blank=True, null=True, default='n/a')
    # Any territory code is accepted; TERRITORY_CHOICES is just the usual list for menus.
    territory      = models.CharField('Territory code', max_length=50, blank=True, null=True)
    email          = models.EmailField(max_length=254, blank=True, default='')
    tip_top = models.BooleanField(default=False)
    taula_fridge = models.BooleanField(default=False)
    talofa_voucher = models.BooleanField(default=False)
    faakau_com = models.BooleanField(default=False)
    created = models.DateField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.name


class ShopPhoto(models.Model):
    """A photo attached to a retail shop. `note` is the optional label."""
    shop    = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='photos')
    image   = models.ImageField(upload_to='shops/%Y/%m/')
    note    = models.CharField(max_length=300, blank=True,
                               help_text='Optional label (e.g. Storefront, License, Cooler)')
    uploaded = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded']

    def __str__(self):
        return f'Photo — {self.shop.name} — {self.note or "no label"}'


# ── HORECCA Businesses ────────────────────────────────────────────────────────

class Business(models.Model):
    BUSINESS_TYPES = [
        ('HOTEL',      'Hotel'),
        ('CAFE',       'Café'),
        ('RESTAURANT', 'Restaurant'),
        ('OTHER',      'Other'),
    ]
    ISLAND_CHOICES = [
        ('Upolu',  'Upolu'),
        ('Savaii', 'Savaii'),
    ]

    name          = models.CharField(max_length=200)
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPES, default='HOTEL')
    island        = models.CharField(max_length=50, choices=ISLAND_CHOICES, default='Upolu',
                                     blank=True, null=True)
    location      = models.CharField(max_length=300, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'HORECCA Client'
        verbose_name_plural = 'HORECCA Clients'

    def __str__(self):
        return f'{self.name} ({self.get_business_type_display()})'


class BusinessPhoto(models.Model):
    """A photo attached to a HORECCA business."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='photos')
    image    = models.ImageField(upload_to='horecca/%Y/%m/')
    note     = models.CharField(max_length=300, blank=True,
                                help_text='Optional label (e.g. Main entrance, Menu board)')
    uploaded = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded']

    def __str__(self):
        return f'Photo — {self.business.name} — {self.note or "no label"}'


# ── Sponsorships ──────────────────────────────────────────────────────────────

class Sponsorship(models.Model):
    TYPE_CHOICES = [
        ('Signage', 'Signage'),
        ('Cooler',  'Cooler'),
        ('Event',   'Event'),
        ('Vehicle', 'Vehicle'),
        ('Uniform', 'Uniform'),
        ('Digital', 'Digital'),
        ('Other',   'Other'),
    ]
    STATUS_CHOICES = [
        ('Active',  'Active'),
        ('Expired', 'Expired'),
        ('Pending', 'Pending'),
    ]
    SPONSORSHIP_TYPE_CHOICES = [
        ('In-Kind Value', 'In-Kind Value'),
        ('Cash Value',    'Cash Value'),
    ]

    customer = models.CharField(max_length=200)
    type     = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Signage')
    sponsorship_type = models.CharField('Sponsorship Type', max_length=20,
                                        choices=SPONSORSHIP_TYPE_CHOICES, default='Cash Value')
    value    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    start    = models.DateField(null=True, blank=True)
    end      = models.DateField(null=True, blank=True)
    notes    = models.TextField(blank=True)
    created  = models.DateField(auto_now_add=True, null=True)

    class Meta:
        # Active first, then Pending, then Expired; newest first within each status
        ordering = [
            models.Case(
                models.When(status='Active',  then=0),
                models.When(status='Pending', then=1),
                models.When(status='Expired', then=2),
                default=3,
            ),
            '-id',
        ]

    def __str__(self):
        return f'{self.customer} — {self.type} ({self.status})'


class SponsorshipPhoto(models.Model):
    """A photo attached to a sponsorship."""
    sponsorship = models.ForeignKey(Sponsorship, on_delete=models.CASCADE, related_name='photos')
    image       = models.ImageField(upload_to='sponsorships/%Y/%m/')
    note        = models.CharField(max_length=300, blank=True,
                                   help_text='Optional label (e.g. Signed agreement, Installed cooler)')
    uploaded    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded']

    def __str__(self):
        return f'Photo — {self.sponsorship} — {self.note or "no label"}'


# ── Surveys ───────────────────────────────────────────────────────────────────

class Survey(models.Model):
    """Staff survey for product performance, market research, and regional data."""
    CATEGORY_CHOICES = [
        ('Product Performance', 'Product Performance'),
        ('Market Research', 'Market Research'),
        ('Regional Sales', 'Regional Sales'),
        ('Customer Feedback', 'Customer Feedback'),
        ('Competitor Analysis', 'Competitor Analysis'),
        ('Other', 'Other'),
    ]
    LOCATION_CHOICES = [
        ('UPOLU', 'Upolu'),
        ('SAVAII', 'Savaii'),
    ]
    REGION_CHOICES = [
        ('1', 'Region 1'),
        ('2', 'Region 2'),
        ('3', 'Region 3'),
        ('4', 'Region 4'),
    ]
    
    title       = models.CharField(max_length=255)
    category    = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Product Performance')
    description = models.TextField(blank=True)
    location    = models.CharField(max_length=100, choices=LOCATION_CHOICES, blank=True)
    region      = models.CharField(max_length=50, choices=REGION_CHOICES, blank=True)
    period      = models.CharField(max_length=50, blank=True)  # e.g., "May-26", "Q2 2026"
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    created_by  = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f'{self.title} — {self.location or self.region or "General"}'
    
    @property
    def response_count(self):
        return self.responses.count()


class SurveyResponse(models.Model):
    """Individual data point/response in a survey."""
    PRODUCT_FIELD_TYPES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('decimal', 'Decimal'),
        ('choice', 'Choice'),
        ('rating', 'Rating'),
    ]

    survey      = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    product     = models.CharField(max_length=255, blank=True)
    customer    = models.CharField(max_length=200, blank=True)  # customer / shop
    period      = models.CharField(max_length=50, blank=True)   # e.g. "May-26", "Q2 2026"
    price       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity    = models.IntegerField(null=True, blank=True)
    location    = models.CharField(max_length=100, blank=True)
    region      = models.CharField(max_length=50, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.CharField(max_length=100, default='Staff')

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f'{self.survey.title} — {self.product or self.customer or "No product/customer"}'


# ── Shop Sales ────────────────────────────────────────────────────────────

class MonthlySales(models.Model):
    """Total sales for one client in one month. Re-uploading a month replaces its total."""
    shop       = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='monthly_sales')
    month      = models.DateField(help_text='Stored as the first day of the month')
    sales      = models.DecimalField(max_digits=14, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-month', 'shop__name']
        verbose_name_plural = 'Monthly sales'
        constraints = [models.UniqueConstraint(fields=['shop', 'month'], name='one_sales_total_per_client_month')]

    def __str__(self):
        return f'{self.shop.name} — {self.month:%b %Y}'

    @property
    def customer_code(self):
        return self.shop.customer_code

    @property
    def customer_name(self):
        return self.shop.name


# ── Promotions ────────────────────────────────────────────────────────────

class Promotion(models.Model):
    """A trade promotion run by one of the partner companies. Status comes from the dates."""
    COMPANY_CHOICES = [
        ('Ah Liki Wholesale', 'Ah Liki Wholesale'),
        ('Farmer Joe',        'Farmer Joe'),
        ('Taula',             'Taula'),
        ('Burger Bills',      'Burger Bills'),
        ('INKPRO',            'INKPRO'),
    ]
    STATUS_CHOICES = [
        ('Active',   'Active'),
        ('Upcoming', 'Upcoming'),
        ('Ended',    'Ended'),
    ]

    name       = models.CharField('Promotion name', max_length=255)
    company    = models.CharField(max_length=50, choices=COMPANY_CHOICES)
    details    = models.TextField(blank=True)
    prizes     = models.TextField(blank=True, help_text='One prize per line, e.g. 1st — WST 500 voucher')
    start_date = models.DateField(null=True, blank=True)
    end_date   = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', 'name']

    def __str__(self):
        return f'{self.company} — {self.name}'

    @property
    def status(self):
        today = datetime.date.today()
        if self.start_date and self.start_date > today:
            return 'Upcoming'
        if self.end_date and self.end_date < today:
            return 'Ended'
        return 'Active'

    @property
    def prize_list(self):
        return [line.strip() for line in self.prizes.splitlines() if line.strip()]

    @staticmethod
    def status_q(status):
        """Filter matching the computed status, for querysets."""
        today = datetime.date.today()
        if status == 'Upcoming':
            return models.Q(start_date__gt=today)
        if status == 'Ended':
            return models.Q(end_date__lt=today) & ~models.Q(start_date__gt=today)
        return ((models.Q(start_date__isnull=True) | models.Q(start_date__lte=today)) &
                (models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)))


# ── Corporate sales targets ────────────────────────────────────────────────

class SalesTarget(models.Model):
    """Monthly sales target for one corporate account manager (see shops/corporate.py)."""
    manager = models.CharField(max_length=30)   # a SalesRep key, e.g. 'grace'
    month   = models.DateField(help_text='Stored as the first day of the month')
    amount  = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['manager', 'month']
        constraints = [models.UniqueConstraint(fields=['manager', 'month'], name='one_target_per_manager_month')]

    def __str__(self):
        return f'{self.manager} — {self.month:%b %Y}: {self.amount}'


# ── Product sales ─────────────────────────────────────────────────────────

class ProductSales(models.Model):
    """Total sales of one product in one month (from the product sales CSV). Re-uploading a month replaces it."""
    product_code = models.CharField(max_length=50, db_index=True)
    product_name = models.CharField(max_length=255)
    month        = models.DateField(help_text='Stored as the first day of the month')
    total_sales  = models.DecimalField(max_digits=14, decimal_places=2)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-month', 'product_name']
        verbose_name_plural = 'Product sales'
        constraints = [models.UniqueConstraint(fields=['product_code', 'month'], name='one_total_per_product_month')]

    def __str__(self):
        return f'{self.product_code} {self.product_name} — {self.month:%b %Y}'


class CustomerProductSales(models.Model):
    """One client's sales of one product in one month (the Customer Product Sales CSV). Drives the Top 10
    products chart on Corporate Sales. Re-uploading a client's product month replaces it."""
    shop         = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='product_sales')
    product_code = models.CharField(max_length=50)
    product_name = models.CharField(max_length=255)
    month        = models.DateField(help_text='Stored as the first day of the month')
    sales        = models.DecimalField(max_digits=14, decimal_places=2)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-month', '-sales']
        verbose_name_plural = 'Customer product sales'
        constraints = [models.UniqueConstraint(fields=['shop', 'product_code', 'month'],
                                               name='one_total_per_client_product_month')]

    def __str__(self):
        return f'{self.shop.name} — {self.product_name} — {self.month:%b %Y}'


class PinnedProduct(models.Model):
    """A product pinned to the quick links on the Product Sales page (shared by the office)."""
    product_code = models.CharField(max_length=50, unique=True)
    pinned_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pinned_at']

    def __str__(self):
        return self.product_code


class ProductGroup(models.Model):
    """A named set of products for the Product Sales quick links, e.g. "Tip Top".

    A product is in the group if its name or code contains any keyword (so new products join
    automatically), or if it was picked by hand (product_codes), unless it was taken out (exclude_codes).
    """
    name          = models.CharField(max_length=100, unique=True)
    keywords      = models.CharField(max_length=255, blank=True, help_text='Comma-separated, e.g. tip top, tiptop')
    product_codes = models.TextField(blank=True, help_text='Products picked by hand, one code per line')
    exclude_codes = models.TextField(blank=True, help_text='Products taken out even if a keyword matches, one code per line')
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def keyword_list(self):
        return [k.strip() for k in self.keywords.split(',') if k.strip()]

    def code_list(self):
        return [c for c in re.split(r'[\s,;]+', self.product_codes) if c]

    def exclude_list(self):
        return [c for c in re.split(r'[\s,;]+', self.exclude_codes) if c]

    def match(self):
        """Filter for ProductSales rows belonging to this group."""
        q = models.Q(pk__in=[])   # matches nothing when the group has no rules
        for word in self.keyword_list():
            q |= models.Q(product_name__icontains=word) | models.Q(product_code__icontains=word)
        if self.code_list():
            q |= models.Q(product_code__in=self.code_list())
        if self.exclude_list():
            q &= ~models.Q(product_code__in=self.exclude_list())
        return q


class QuickLinkTarget(models.Model):
    """A monthly target set by hand for a product group or a pinned product.
    Months without one fall back to the same month last year."""
    group        = models.ForeignKey(ProductGroup, null=True, blank=True, on_delete=models.CASCADE, related_name='targets')
    product_code = models.CharField(max_length=50, blank=True)
    month        = models.DateField(help_text='Stored as the first day of the month')
    amount       = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['month']
        constraints = [
            models.UniqueConstraint(fields=['group', 'month'], condition=models.Q(group__isnull=False),
                                    name='one_target_per_group_month'),
            models.UniqueConstraint(fields=['product_code', 'month'], condition=~models.Q(product_code=''),
                                    name='one_target_per_product_month'),
        ]

    def __str__(self):
        return f'{self.group or self.product_code} — {self.month:%b %Y}: {self.amount}'


class SalesRep(models.Model):
    """A corporate account manager on the Corporate Sales page (e.g. Grace). Clients are theirs when the
    client's Customer Type contains one of their keywords. Edited in the admin panel."""
    key            = models.SlugField(max_length=30, unique=True,
                                      help_text='Short id used in links and targets, e.g. grace. Can’t be changed later.')
    name           = models.CharField(max_length=60)
    streams        = models.CharField(max_length=255, help_text='Shown on their card, comma-separated, e.g. Ministries, Finance & Banks')
    customer_types = models.TextField('Customer type keywords',
                                      help_text='Comma-separated. A client is theirs if its Customer Type contains any of these '
                                                '(from the start of a word, ignoring capitals), e.g. ministr, laundr, bank')
    color          = models.CharField(max_length=7, default='#0EA5E9', help_text='Card and graph colour, e.g. #7C3AED')
    order          = models.PositiveIntegerField(default=0, help_text='Position on the page, lowest first')
    active         = models.BooleanField(default=True, help_text='Untick to hide them from Corporate Sales (targets are kept)')
    user           = models.OneToOneField('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_rep',
                                          help_text='Their login. Unless they’re a Manager, Corporate Sales then shows only '
                                                    'their own stream, plus every rep’s % of this month’s target.')

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Sales rep'

    def __str__(self):
        return self.name

    def stream_list(self):
        return [s.strip() for s in re.split(r'[,\n]', self.streams) if s.strip()]

    def keyword_list(self):
        # one per line works too, not just comma-separated
        return [k.strip().lower() for k in re.split(r'[,\n]', self.customer_types) if k.strip()]

    def matches(self, customer_type):
        text = (customer_type or '').lower()
        return any(re.search(r'\b' + re.escape(k), text) for k in self.keyword_list())
