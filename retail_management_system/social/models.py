import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone

# The companies whose pages are tracked, in the order they appear everywhere
COMPANIES = [
    ('ah_liki_wholesale',   'Ah Liki Wholesale'),
    ('farmer_joe',          'Farmer Joe'),
    ('burger_bills',        'Burger Bills'),
    ('natural_samoa_water', 'Natural Samoa Water'),
    ('ink_pro',             'Ink Pro'),
]
PLATFORMS = [('facebook', 'Facebook'), ('instagram', 'Instagram')]

# The numbers are updated every Monday and Saturday (date.weekday())
UPDATE_DAYS = (0, 5)


def office_today():
    """Today's date in the office (Samoa)."""
    from zoneinfo import ZoneInfo
    return timezone.localdate(timezone=ZoneInfo(settings.CAR_TIME_ZONE))


def is_update_day(day):
    return day.weekday() in UPDATE_DAYS


def last_update_day(today=None):
    """The latest Monday or Saturday on or before today: the update that should be in by now."""
    day = today or office_today()
    while not is_update_day(day):
        day -= datetime.timedelta(days=1)
    return day


def next_update_day(today=None):
    """The next Monday or Saturday after today."""
    day = (today or office_today()) + datetime.timedelta(days=1)
    while not is_update_day(day):
        day += datetime.timedelta(days=1)
    return day


class SocialCount(models.Model):
    """One company's follower numbers on one update day (a Monday or Saturday)."""
    company    = models.CharField(max_length=30, choices=COMPANIES)
    date       = models.DateField()
    facebook   = models.PositiveIntegerField('Facebook', null=True, blank=True, help_text='Page followers')
    instagram  = models.PositiveIntegerField('Instagram', null=True, blank=True, help_text='Account followers')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'company']
        constraints = [models.UniqueConstraint(fields=['company', 'date'], name='social_count_once_per_day')]
        verbose_name = 'social number'

    def __str__(self):
        return f'{self.get_company_display()} · {self.date:%d %b %Y}'
