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
    ]

    name    = models.CharField(max_length=255)
    owner   = models.CharField(max_length=255, blank=True, null=True, default='n/a')
    phone   = models.CharField(max_length=15,  blank=True, null=True, default='n/a')
    address = models.CharField(max_length=255, blank=True, null=True, default='n/a')
    island  = models.CharField(max_length=50,  choices=ISLAND_CHOICES, default='Upolu')
    territory = models.CharField(max_length=50, choices=TERRITORY_CHOICES, blank=True, null=True)
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

    customer = models.CharField(max_length=200)
    type     = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Signage')
    value    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    start    = models.DateField(null=True, blank=True)
    end      = models.DateField(null=True, blank=True)
    notes    = models.TextField(blank=True)
    created  = models.DateField(auto_now_add=True, null=True)

    class Meta:
        ordering = ['-id']

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
    category    = models.CharField(max_length=100, blank=True)
    customer    = models.CharField(max_length=200, blank=True)
    location    = models.CharField(max_length=100, blank=True)
    region      = models.CharField(max_length=50, blank=True)
    week        = models.IntegerField(null=True, blank=True)
    price       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity    = models.IntegerField(null=True, blank=True)
    rating      = models.IntegerField(null=True, blank=True)  # 1-5 scale
    notes       = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.CharField(max_length=100, default='Staff')

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f'{self.survey.title} — {self.product or self.customer or "No product/customer"}'


# ── Shop Sales ────────────────────────────────────────────────────────────

class ShopSales(models.Model):
    """Sales data for retail shops."""
    shop       = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='sales')
    products   = models.CharField(max_length=500, blank=True, null=True)
    quantity   = models.IntegerField(blank=True, null=True)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    date       = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        verbose_name_plural = 'Shop Sales'

    def __str__(self):
        return f'{self.shop.name} — {self.date or "No date"}'
