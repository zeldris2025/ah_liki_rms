from django.conf import settings
from django.db import models

# The company cars Sales and Marketing can book, in the order their buttons appear.
CARS = ['81', '82', 'Ringo', 'Ranger']
# Finance's own cars: only Finance see and book them, and only a Financial Controller is told about and
# approves them (never admins or Managers).
FINANCE_CARS = ['Raize 18', 'Raize 17']
ALL_CARS = CARS + FINANCE_CARS


class Booking(models.Model):
    """One car booked by one person for a stretch of time. Bookings for the same car may not overlap.
    Staff bookings wait for a Manager (a Financial Controller, for the Finance cars) to approve or decline them;
    a declined booking frees the slot."""
    PENDING, APPROVED, DECLINED = 'pending', 'approved', 'declined'
    STATUSES = [(PENDING, 'Waiting for approval'), (APPROVED, 'Approved'), (DECLINED, 'Declined')]

    car        = models.CharField(max_length=20, choices=[(c, c) for c in ALL_CARS])
    start      = models.DateTimeField()
    end        = models.DateTimeField()
    reason     = models.CharField(max_length=255)
    booked_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='car_bookings')
    created_at = models.DateTimeField(auto_now_add=True)
    email_status = models.CharField(max_length=120, blank=True, help_text='Result of the Microsoft 365 email notification')
    status       = models.CharField(max_length=10, choices=STATUSES, default=PENDING, db_index=True)
    decline_reason = models.TextField(blank=True, help_text="The Manager's comment when declining")
    decided_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='car_bookings_decided')
    decided_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['start']
        indexes = [models.Index(fields=['car', 'start', 'end'])]

    def __str__(self):
        return f'{self.car}: {self.start:%d %b %H:%M} to {self.end:%d %b %H:%M}'

    @property
    def booked_by_name(self):
        return self.booked_by.get_full_name() or self.booked_by.username

    @classmethod
    def clashes(cls, car, start, end, exclude_pk=None):
        """Live (pending or approved) bookings for this car that overlap start-end (touching end-to-start is fine)."""
        qs = cls.objects.filter(car=car, start__lt=end, end__gt=start).exclude(status=cls.DECLINED)
        return qs.exclude(pk=exclude_pk) if exclude_pk else qs


class Notification(models.Model):
    """An in-app notice shown under the bell, e.g. when a colleague books a car."""
    recipient  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message    = models.CharField(max_length=255)
    link       = models.CharField(max_length=255, blank=True)
    booking    = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    created_at = models.DateTimeField(auto_now_add=True)
    read       = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', 'read'])]

    def __str__(self):
        return self.message
