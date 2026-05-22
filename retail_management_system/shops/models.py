from django.db import models


# ── Retail Shops ──────────────────────────────────────────────────────────────

class Shop(models.Model):
    ISLAND_CHOICES = [
        ('Upolu',  'Upolu'),
        ('Savaii', 'Savaii'),
    ]
    REGION_CHOICES = [
        ('Region 1', 'Region 1'),
        ('Region 2', 'Region 2'),
        ('Region 3', 'Region 3'),
        ('Region 4', 'Region 4'),
    ]

    name    = models.CharField(max_length=255)
    owner   = models.CharField(max_length=255, blank=True, null=True, default='n/a')
    phone   = models.CharField(max_length=15,  blank=True, null=True, default='n/a')
    address = models.CharField(max_length=255, blank=True, null=True, default='n/a')
    island  = models.CharField(max_length=50,  choices=ISLAND_CHOICES, default='Upolu')
    region  = models.CharField(max_length=50,  choices=REGION_CHOICES, default='Region 1')
    tip_top = models.BooleanField(default=False)
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
