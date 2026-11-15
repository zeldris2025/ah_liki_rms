from django.db import migrations

SITES = [
    ('ALW HQ', '#0D2D5A'),
    ('ALW SAVAII', '#0EA5E9'),
    ('ALW VAITELE', '#16A34A'),
    ('ALW TAUFUSI', '#EA580C'),
]


def seed(apps, schema_editor):
    Site = apps.get_model('shops', 'Site')
    for order, (name, color) in enumerate(SITES):
        Site.objects.get_or_create(name=name, defaults={'color': color, 'order': order})


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0044_site_sales'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
