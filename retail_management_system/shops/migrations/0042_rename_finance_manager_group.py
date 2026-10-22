from django.db import migrations


def rename(apps, old, new):
    Group = apps.get_model('auth', 'Group')
    if not Group.objects.filter(name=new).exists():
        Group.objects.filter(name=old).update(name=new)   # keeps everyone already in the group
    else:
        Group.objects.get_or_create(name=new)


def forwards(apps, schema_editor):
    rename(apps, 'Finance Manager', 'Financial Controller')


def backwards(apps, schema_editor):
    rename(apps, 'Financial Controller', 'Finance Manager')


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0041_finance_access_groups'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
