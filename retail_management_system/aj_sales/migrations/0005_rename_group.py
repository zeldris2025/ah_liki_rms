"""Rename the 'AJ' group to 'Product QTY Sales', keeping everyone in it."""
from django.db import migrations

OLD, NEW = 'AJ', 'Product QTY Sales'


def rename(old, new):
    def run(apps, schema_editor):
        Group = apps.get_model('auth', 'Group')
        if not Group.objects.filter(name=new).exists():
            Group.objects.filter(name=old).update(name=new)
    return run


class Migration(migrations.Migration):

    dependencies = [
        ('aj_sales', '0004_remove_product_comparison'),
    ]

    operations = [
        migrations.RunPython(rename(OLD, NEW), rename(NEW, OLD)),
    ]
