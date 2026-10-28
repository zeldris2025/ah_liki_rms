"""Starting content: the departments and role titles Ah Liki gave for Career Connect, the portal settings row, and
an empty 'Career Connect Admin' group holding the management permissions (nobody is added to it).

Only names go in: descriptions, requirements and vacancy status are left blank / 'Not stated' for an administrator
to fill in, so the public pages say 'not provided yet' instead of showing made-up details.
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

DEPARTMENTS = [
    # (slug, name, icon, [(role slug, role title), ...])
    ('finance', 'Finance Department', '💰', [
        ('accountant', 'Accountant'),
        ('finance-officer', 'Finance Officer'),
        ('inventory-executive-officer', 'Inventory Executive Officer'),
    ]),
    ('marketing', 'Marketing Department', '📣', [
        ('field-executive-officer', 'Field Executive Officer'),
        ('graphics-designer', 'Graphics Designer'),
    ]),
    ('hr', 'HR Department', '🧑‍🏫', [
        ('training-and-development-officer', 'Training and Development Officer'),
    ]),
    ('sales', 'Sales Department', '🛒', [
        ('cashier-sales-representative', 'Cashier & Sales Representative'),
    ]),
    ('warehouse-operation', 'Warehouse Operation', '📦', [
        ('warehouse-assistant-loader', 'Warehouse Assistant / Loader'),
    ]),
    ('trades', 'Trades Department', '🔧', [
        ('carpenters', 'Carpenters'),
        ('welders', 'Welders'),
        ('engineers', 'Engineers'),
    ]),
]

GROUP = 'Career Connect Admin'
GROUP_PERMS = ['manage_career_connect', 'view_portalsettings', 'change_portalsettings',
               'add_department', 'change_department', 'delete_department', 'view_department',
               'add_role', 'change_role', 'delete_role', 'view_role',
               'add_companyimage', 'change_companyimage', 'delete_companyimage', 'view_companyimage',
               'change_expressionofinterest', 'delete_expressionofinterest', 'view_expressionofinterest']


def seed(apps, schema_editor):
    PortalSettings = apps.get_model('career_connect', 'PortalSettings')
    Department = apps.get_model('career_connect', 'Department')
    Role = apps.get_model('career_connect', 'Role')
    PortalSettings.objects.get_or_create(pk=1)
    for d_order, (slug, name, icon, roles) in enumerate(DEPARTMENTS, start=1):
        dept, _ = Department.objects.get_or_create(slug=slug, defaults={'name': name, 'icon': icon, 'order': d_order})
        for r_order, (r_slug, title) in enumerate(roles, start=1):
            Role.objects.get_or_create(department=dept, slug=r_slug, defaults={'title': title, 'order': r_order})

    # Permissions are normally created after all migrations; make sure they exist for the group now
    app_config = apps.get_app_config('career_connect')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    group, _ = Group.objects.get_or_create(name=GROUP)
    group.permissions.add(*Permission.objects.filter(content_type__app_label='career_connect',
                                                     codename__in=GROUP_PERMS))


def unseed(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [migrations.RunPython(seed, unseed)]
