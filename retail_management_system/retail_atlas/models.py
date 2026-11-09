from django.core.exceptions import ValidationError
from django.db import models

from shops.models import Shop

# Generous box around Upolu, Savaii, Manono and Apolima; rejects stray clicks.
SAMOA_BOUNDS = {'south': -14.20, 'north': -13.30, 'west': -172.85, 'east': -171.30}


def check_in_samoa(latitude, longitude):
    """ValidationError unless the point is inside SAMOA_BOUNDS (blank values are left to the field checks)."""
    if latitude is None or longitude is None:
        return
    b = SAMOA_BOUNDS
    if not (b['south'] <= float(latitude) <= b['north'] and b['west'] <= float(longitude) <= b['east']):
        raise ValidationError('That point is outside Samoa. Click the map to place it.')


class ShopLocation(models.Model):
    """A pin dropped by hand on the atlas map.

    Shops without one are placed automatically from the village named in
    their address (see gazetteer.py). A manual pin always wins.
    """
    shop       = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='atlas_location')
    latitude   = models.DecimalField(max_digits=9, decimal_places=6)
    longitude  = models.DecimalField(max_digits=9, decimal_places=6)
    updated_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Shop Location'
        verbose_name_plural = 'Shop Locations'

    def __str__(self):
        return f'{self.shop.name} ({self.latitude}, {self.longitude})'

    def clean(self):
        check_in_samoa(self.latitude, self.longitude)


class CompanyLocation(models.Model):
    """One of our own companies' sites (head office, branch, warehouse, farm…), shown as its own layer on the
    atlas. Added and moved in the Django admin by clicking its map."""
    KINDS = [
        ('head_office', 'Head office'),
        ('branch',      'Branch / outlet'),
        ('supermarket', 'Supermarket'),
        ('restaurant',  'Restaurant'),
        ('warehouse',   'Warehouse'),
        ('factory',     'Factory'),
        ('farm',        'Farm'),
        ('other',       'Other'),
    ]

    company      = models.CharField(max_length=120, help_text='e.g. Farmer Joe. Sites of the same company share a colour on the map.')
    name         = models.CharField('site name', max_length=150, help_text='e.g. Farmer Joe Vaitele')
    kind         = models.CharField('type', max_length=20, choices=KINDS, default='branch')
    address      = models.CharField(max_length=255, blank=True)
    phone        = models.CharField(max_length=50, blank=True)
    notes        = models.TextField(blank=True, help_text='Shown in the map popup, e.g. opening hours.')
    latitude     = models.DecimalField(max_digits=9, decimal_places=6)
    longitude    = models.DecimalField(max_digits=9, decimal_places=6)
    is_published = models.BooleanField('show on the Atlas', default=True)
    updated_by   = models.CharField(max_length=150, blank=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('company', 'name')
        verbose_name = 'Company Location'
        verbose_name_plural = 'Company Locations'

    def __str__(self):
        return self.name

    def clean(self):
        check_in_samoa(self.latitude, self.longitude)
