"""Makes the audit log entries.

AuditMiddleware remembers the request being handled; the model signals below record each add, change and delete
made while a signed-in person's request is running (so migrations, management commands and the public Career
Connect forms aren't logged). Changes made with QuerySet.update() or bulk_create() skip Django's signals and so
aren't logged either.
"""
import contextvars
import datetime
import decimal

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import AuditEntry

_request = contextvars.ContextVar('audit_request', default=None)

# Never logged: the log itself, sign-in sessions and Django's own bookkeeping
SKIP_MODELS = {('audit', 'auditentry'), ('sessions', 'session'), ('admin', 'logentry'),
               ('contenttypes', 'contenttype'), ('auth', 'permission')}
SKIP_FIELDS = {'last_login', 'updated_at', 'modified', 'created_at'}
SECRET_FIELDS = {'password'}
MAX_VALUE = 300   # characters kept of a long value


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)


def _actor():
    request = _request.get()
    user = getattr(request, 'user', None) if request else None
    if user is None or not user.is_authenticated:
        return None, None
    return request, user


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (forwarded.split(',')[-1].strip() if forwarded else request.META.get('REMOTE_ADDR', ''))[:64]


def _skip(sender):
    meta = sender._meta
    return (meta.app_label, meta.model_name) in SKIP_MODELS or not meta.managed


def _fields(instance):
    return [f for f in instance._meta.concrete_fields if f.name not in SKIP_FIELDS and not f.primary_key]


def _show(field, value):
    """A value as it reads in the log: related items by name, files by file name, long text cut short."""
    if value is None or value == '':
        return None
    if field.name in SECRET_FIELDS:
        return '••••••'
    if isinstance(field, models.ForeignKey):
        related = field.related_model._base_manager.filter(pk=value).first()
        return str(related) if related is not None else f'#{value}'
    if field.choices:
        value = dict(field.flatchoices).get(value, value)
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat(sep=' ', timespec='minutes') if isinstance(value, datetime.datetime) else value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (bool, int, float)):
        return value
    if hasattr(value, 'name'):   # a file
        value = value.name or None
        if value is None:
            return None
    text = str(value)
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE] + '…'


def _record(instance, action, changes, request, user):
    AuditEntry.objects.create(
        user=user, username=user.get_username(), action=action,
        content_type=ContentType.objects.get_for_model(instance, for_concrete_model=False),
        object_id=str(instance.pk or '')[:64], object_repr=str(instance)[:200], changes=changes,
        path=request.path[:300], ip=_client_ip(request))


@receiver(pre_save, dispatch_uid='audit_pre_save')
def _before_save(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or _skip(sender) or _actor()[1] is None:
        return
    instance._audit_old = None
    if instance.pk is not None:
        names = [f.attname for f in _fields(instance)]
        instance._audit_old = sender._base_manager.filter(pk=instance.pk).values(*names).first()


@receiver(post_save, dispatch_uid='audit_post_save')
def _after_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    request, user = _actor()
    if raw or _skip(sender) or user is None:
        return
    old = getattr(instance, '_audit_old', None)
    changes = {}
    for f in _fields(instance):
        if update_fields is not None and f.name not in update_fields and f.attname not in update_fields:
            continue
        new = getattr(instance, f.attname)
        before = old.get(f.attname) if old else None
        if old is not None and before == new:
            continue
        if old is None and new in (None, '', False) and not created:
            continue
        shown_old, shown_new = (_show(f, before) if old is not None else None), _show(f, new)
        if created and shown_new is None:
            continue
        if shown_old != shown_new or f.name in SECRET_FIELDS:
            changes[str(f.verbose_name)] = [shown_old, shown_new]
    if created or old is None:
        _record(instance, AuditEntry.ADDED, changes, request, user)
    elif changes:
        _record(instance, AuditEntry.CHANGED, changes, request, user)


@receiver(post_delete, dispatch_uid='audit_post_delete')
def _after_delete(sender, instance, **kwargs):
    request, user = _actor()
    if _skip(sender) or user is None:
        return
    changes = {}
    for f in _fields(instance):
        try:
            shown = _show(f, getattr(instance, f.attname))
        except Exception:   # a related row already gone in the same delete
            shown = None
        if shown is not None:
            changes[str(f.verbose_name)] = [shown, None]
    _record(instance, AuditEntry.DELETED, changes, request, user)


@receiver(m2m_changed, dispatch_uid='audit_m2m')
def _many_to_many(sender, instance, action, reverse, model, pk_set, **kwargs):
    """e.g. a user's groups or permissions."""
    request, user = _actor()
    if action not in ('post_add', 'post_remove', 'post_clear') or user is None or _skip(type(instance)):
        return
    field = next((f for f in type(instance)._meta.many_to_many if f.remote_field.through is sender), None)
    label = field.verbose_name if field else model._meta.verbose_name_plural
    names = ', '.join(sorted(str(o) for o in model._base_manager.filter(pk__in=pk_set or ()))) or 'all'
    change = {'post_add': [None, f'added {names}'], 'post_remove': [f'removed {names}', None],
              'post_clear': ['cleared', None]}[action]
    _record(instance, AuditEntry.CHANGED, {str(label): change}, request, user)
