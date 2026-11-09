"""The 'AJ' group: people in it upload quantity sales and see the AJ dashboard, analytics and Product QTY.
Nobody is added to it here."""
from django.db import migrations

AJ_GROUP = 'AJ'


def create_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.get_or_create(name=AJ_GROUP)


def remove_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=AJ_GROUP, user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('aj_sales', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
