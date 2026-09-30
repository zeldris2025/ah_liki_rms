from django.db import migrations

ROLES = ('Sales', 'Marketing', 'Manager')


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in ROLES:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0034_sponsorship_type_inkpro'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
