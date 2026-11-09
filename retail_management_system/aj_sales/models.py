import re

from django.db import models


class QtySales(models.Model):
    """Quantity sold of one product in one month (the Product QTY Sales CSV). Re-uploading a month replaces it."""
    product_code = models.CharField(max_length=50, db_index=True)
    product_name = models.CharField(max_length=255, blank=True)
    month        = models.DateField(help_text='Stored as the first day of the month')
    qty          = models.DecimalField('QTY', max_digits=14, decimal_places=2)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-month', '-qty']
        verbose_name = 'product QTY'
        verbose_name_plural = 'Product QTY'
        constraints = [models.UniqueConstraint(fields=['product_code', 'month'], name='one_qty_per_product_month')]

    def __str__(self):
        return f'{self.product_name or self.product_code} — {self.month:%b %Y}'


# ── Quick links: pinned products and product groups, measured against a monthly QTY target ──

class QtyPinnedProduct(models.Model):
    """A product pinned to the quick links on Product QTY (shared by everyone who uses Product QTY Sales)."""
    product_code = models.CharField(max_length=50, unique=True)
    pinned_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pinned_at']
        verbose_name = 'pinned product'

    def __str__(self):
        return self.product_code


class QtyProductGroup(models.Model):
    """A named set of products for the Product QTY quick links, e.g. "Tip Top".

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
        verbose_name = 'product group'

    def __str__(self):
        return self.name

    def keyword_list(self):
        return [k.strip() for k in self.keywords.split(',') if k.strip()]

    def code_list(self):
        return [c for c in re.split(r'[\s,;]+', self.product_codes) if c]

    def exclude_list(self):
        return [c for c in re.split(r'[\s,;]+', self.exclude_codes) if c]

    def match(self):
        """Filter for QtySales rows belonging to this group."""
        q = models.Q(pk__in=[])   # matches nothing when the group has no rules
        for word in self.keyword_list():
            q |= models.Q(product_name__icontains=word) | models.Q(product_code__icontains=word)
        if self.code_list():
            q |= models.Q(product_code__in=[c.upper() for c in self.code_list()])
        if self.exclude_list():
            q &= ~models.Q(product_code__in=[c.upper() for c in self.exclude_list()])
        return q


class QtyTarget(models.Model):
    """A monthly QTY target set by hand for a group or a pinned product.
    Months without one fall back to the same month last year."""
    group        = models.ForeignKey(QtyProductGroup, null=True, blank=True, on_delete=models.CASCADE, related_name='targets')
    product_code = models.CharField(max_length=50, blank=True)
    month        = models.DateField(help_text='Stored as the first day of the month')
    qty          = models.DecimalField('QTY', max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['month']
        verbose_name = 'QTY target'
        constraints = [
            models.UniqueConstraint(fields=['group', 'month'], condition=models.Q(group__isnull=False),
                                    name='one_qty_target_per_group_month'),
            models.UniqueConstraint(fields=['product_code', 'month'], condition=~models.Q(product_code=''),
                                    name='one_qty_target_per_product_month'),
        ]

    def __str__(self):
        return f'{self.group or self.product_code} — {self.month:%b %Y}: {self.qty}'
