from django.db import migrations

# The four reps that were built into the code, with the same client matching as before
REPS = [
    ('grace', 'Grace', 'Tokelau, NGOs, Pharmacies', 'tokelau, ngo, non-gov, non gov, nongov, pharmac', '#0EA5E9'),
    ('ruth', 'Ruth', 'Ministries, Finance & Banks, Laundromats', 'ministr, financ, bank, laundr', '#7C3AED'),
    ('judane', 'Judane', 'HORECA', 'horeca, horecca, hotel, restaurant, cafe, café, catering, resort', '#16A34A'),
    ('ivan', 'Ivan', 'Retail & Supermarkets', 'retail, supermarket', '#EA580C'),
]


def seed(apps, schema_editor):
    SalesRep = apps.get_model('shops', 'SalesRep')
    for order, (key, name, streams, keywords, color) in enumerate(REPS):
        SalesRep.objects.get_or_create(key=key, defaults={
            'name': name, 'streams': streams, 'customer_types': keywords, 'color': color, 'order': order})


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0032_sales_reps'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
