from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from career_connect.models import Company, Employee

from .models import AuditEntry


class AuditLogTests(TestCase):
    """Every add, change and delete made by someone signed in is logged: who, what, when, before and after."""

    def setUp(self):
        self.boss = User.objects.create_superuser('boss', 'boss@example.com', 'pw-123456')
        self.client.force_login(self.boss)
        self.fj = Company.objects.get(slug='farmer-joe')

    def test_admin_changes_are_logged_with_before_and_after(self):
        url = reverse('admin:career_connect_employee_add')
        self.client.post(url, {'company': self.fj.pk, 'first_name': 'Jane', 'last_name': 'Doe', 'status': 'active'})
        jane = Employee.objects.get()
        added = AuditEntry.objects.get(action='added')
        self.assertEqual((added.username, added.object_repr, added.object_id), ('boss', 'Jane Doe', str(jane.pk)))
        self.assertEqual(added.changes['company'], [None, 'Farmer Joe'])
        self.assertEqual(added.path, url)

        self.client.post(reverse('admin:career_connect_employee_change', args=[jane.pk]), {
            'company': self.fj.pk, 'first_name': 'Jane', 'last_name': 'Smith', 'status': 'active'})
        changed = AuditEntry.objects.get(action='changed')
        self.assertEqual(changed.changes, {'last name': ['Doe', 'Smith']})

        self.client.post(reverse('admin:career_connect_employee_delete', args=[jane.pk]), {'post': 'yes'})
        deleted = AuditEntry.objects.get(action='deleted')
        self.assertEqual(deleted.changes['first name'], ['Jane', None])

    def test_changes_on_the_sms_pages_are_logged_too(self):
        hr = User.objects.create_user('hr', password='pw-123456')
        hr.groups.add(Group.objects.get_or_create(name='HR')[0])
        self.client.force_login(hr)
        self.client.post(reverse('hr_employee_add'), {'company': self.fj.pk, 'first_name': 'Sam', 'status': 'active'})
        self.assertEqual(AuditEntry.objects.get().username, 'hr')

    def test_passwords_and_group_changes(self):
        u = User.objects.create_user('sione', password='pw-123456')
        sales = Group.objects.get_or_create(name='Sales')[0]
        AuditEntry.objects.all().delete()
        self.client.post(reverse('admin:auth_user_change', args=[u.pk]), {
            'username': 'sione', 'is_active': 'on', 'groups': [sales.pk],
            'date_joined_0': '2026-01-01', 'date_joined_1': '00:00:00'})
        entries = [str(c) for c in AuditEntry.objects.values_list('changes', flat=True)]
        self.assertTrue(any('added Sales' in c for c in entries), entries)
        self.client.post(reverse('admin:auth_user_password_change', args=[u.pk]), {
            'password1': 'New-pass-98765', 'password2': 'New-pass-98765', 'usable_password': 'true'})
        entries = [str(c) for c in AuditEntry.objects.values_list('changes', flat=True)]
        self.assertTrue(any('password' in c for c in entries), entries)
        self.assertFalse(any('pbkdf2' in c for c in entries), entries)

    def test_nothing_is_logged_without_someone_signed_in(self):
        self.client.logout()
        Employee.objects.create(company=self.fj, first_name='Script')
        self.assertFalse(AuditEntry.objects.exists())

    def test_the_log_cant_be_edited(self):
        self.client.post(reverse('admin:career_connect_employee_add'),
                         {'company': self.fj.pk, 'first_name': 'Y', 'status': 'active'})
        entry = AuditEntry.objects.first()
        self.assertEqual(self.client.get(reverse('admin:audit_auditentry_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:audit_auditentry_change', args=[entry.pk])).status_code, 200)
        self.client.post(reverse('admin:audit_auditentry_delete', args=[entry.pk]), {'post': 'yes'})
        self.assertTrue(AuditEntry.objects.filter(pk=entry.pk).exists())
        self.assertEqual(self.client.get(reverse('admin:audit_auditentry_add')).status_code, 403)
