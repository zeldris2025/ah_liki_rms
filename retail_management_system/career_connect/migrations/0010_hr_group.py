"""The 'HR' group: people in it post and update vacancies for every company on the HR vacancies page, and see
nothing else of the SMS. Nobody is added to it here. The 'Career Connect Admin' group gets the page too."""
from django.contrib.auth.management import create_permissions
from django.db import migrations

HR_GROUP = 'HR'
ADMIN_GROUP = 'Career Connect Admin'
PERMISSION = 'manage_vacancies'


def create_group(apps, schema_editor):
    # Permissions are normally created after all migrations; make sure this one exists now
    app_config = apps.get_app_config('career_connect')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    perm = Permission.objects.get(content_type__app_label='career_connect', codename=PERMISSION)
    Group.objects.get_or_create(name=HR_GROUP)[0].permissions.add(perm)
    admin_group = Group.objects.filter(name=ADMIN_GROUP).first()
    if admin_group:
        admin_group.permissions.add(perm)


def remove_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=HR_GROUP, user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0009_vacancy_permission'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
