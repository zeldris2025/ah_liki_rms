from django.db import models

from shops.models import Shop


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
