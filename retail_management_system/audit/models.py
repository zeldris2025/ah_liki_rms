"""The audit log: who changed what, and when.

Every add, change and delete that a signed-in person makes (in the Django admin or on the SMS pages) is recorded
with the fields that changed, their old and new values, and the page it was done from. See audit.signals for how
the entries are made. Entries can't be added, edited or removed, not even in the admin.
"""
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditEntry(models.Model):
    ADDED, CHANGED, DELETED = 'added', 'changed', 'deleted'
    ACTIONS = [(ADDED, 'Added'), (CHANGED, 'Changed'), (DELETED, 'Deleted')]

    at = models.DateTimeField('when', auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='+')
    username = models.CharField('who', max_length=150, help_text='Kept even if the user is later removed.')
    action = models.CharField(max_length=10, choices=ACTIONS, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, related_name='+',
                                     verbose_name='what')
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField('item', max_length=200)
    changes = models.JSONField(default=dict, blank=True,
                               help_text='Each changed field: [old value, new value].')
    path = models.CharField('page', max_length=300, blank=True)
    ip = models.CharField('IP address', max_length=64, blank=True)

    class Meta:
        ordering = ('-at', '-pk')
        verbose_name = 'audit log entry'
        verbose_name_plural = 'audit log'

    def __str__(self):
        return f'{self.username} {self.action} {self.object_repr}'

    @property
    def model_name(self):
        return self.content_type.model_class()._meta.verbose_name.capitalize() if (
            self.content_type and self.content_type.model_class()) else '—'
