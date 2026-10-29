"""The 'Social' group: people in it keep the companies' Facebook and Instagram numbers up to date (Social #s)
and see the Social dashboard and analytics, the Atlas and Car Allocations. Nobody is added to it here."""
from django.db import migrations

SOCIAL_GROUP = 'Social'


def create_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.get_or_create(name=SOCIAL_GROUP)


def remove_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=SOCIAL_GROUP, user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('social', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
