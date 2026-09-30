from django.conf import settings
from django.db import models

from shops.models import Shop


class Product(models.Model):
    """Catalogue item FE staff can order. Managed by the office on the Products page."""
    product_no = models.CharField(max_length=50, blank=True, help_text='Product code from the office system, e.g. 10045')
    name       = models.CharField(max_length=255, unique=True)
    category   = models.CharField(max_length=100, help_text='Shown as a filter button, e.g. Soda, Water, Snacks')
    unit       = models.CharField(max_length=50, blank=True, help_text='Unit of measure code, e.g. CTN, CASE, EA')
    cost       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                     help_text='WST cost per unit. Office only; FE staff never see it.')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                     help_text='WST per unit. Leave blank if the office prices the order.')
    unit_price_incl_vat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                              help_text='WST per unit including VAT')
    available  = models.BooleanField(default=True, help_text='Untick when out of stock; FE staff see it greyed out')
    quick_link = models.CharField(max_length=50, blank=True,
                                  help_text='Big shortcut button on the Place Order screen, e.g. Tip Top, Meat, Dairy')

    class Meta:
        ordering = ['category', 'name']
        constraints = [
            models.UniqueConstraint(fields=['product_no'], condition=~models.Q(product_no=''),
                                    name='unique_product_no'),
        ]

    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending',   'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    ]

    shop       = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='fe_orders')
    address    = models.CharField(max_length=255, blank=True, help_text='Delivery address, filled from the shop')
    phone      = models.CharField(max_length=30, blank=True, help_text='Contact phone, filled from the shop')
    notes      = models.TextField(blank=True)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    placed_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='fe_orders')
    telegram_status = models.CharField(max_length=120, blank=True, help_text='Result of the Telegram group notification')
    email_status    = models.CharField(max_length=120, blank=True, help_text='Result of the Microsoft 365 email notification')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.number} — {self.shop.name}'

    @property
    def number(self):
        return f'ORD-{self.pk:05d}'

    @property
    def total(self):
        return sum((i.line_total for i in self.items.all() if i.line_total is not None), 0)

    @property
    def item_count(self):
        return sum(i.quantity for i in self.items.all())


class OrderItem(models.Model):
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product    = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='order_items')
    quantity   = models.PositiveIntegerField()
    # Price at the time of ordering, so later price changes don't rewrite history.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f'{self.quantity} × {self.product.name}'

    @property
    def line_total(self):
        return None if self.unit_price is None else self.unit_price * self.quantity


class Issue(models.Model):
    CATEGORY_CHOICES = [
        ('Fridge / Cooler',     'Fridge / Cooler'),
        ('Stock / Delivery',    'Stock / Delivery'),
        ('Pricing',             'Pricing'),
        ('Payment',             'Payment'),
        ('Signage / Promotion', 'Signage / Promotion'),
        ('Competitor',          'Competitor'),
        ('Other',               'Other'),
    ]
    STATUS_CHOICES = [
        ('Open',        'Open'),
        ('In Progress', 'In Progress'),
        ('Resolved',    'Resolved'),
    ]

    shop        = models.ForeignKey(Shop, on_delete=models.SET_NULL, null=True, blank=True, related_name='fe_issues')
    category    = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    description = models.TextField()
    photo       = models.ImageField(upload_to='fe_issues/%Y/%m/', blank=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='fe_issues')
    email_status = models.CharField(max_length=120, blank=True, help_text='Result of the Microsoft 365 email notification')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.category} — {self.shop or "No shop"} ({self.status})'
