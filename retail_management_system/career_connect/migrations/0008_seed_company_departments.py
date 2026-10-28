"""Every other company in the group gets the same departments as Ah Liki Wholesale (names, icons and colours only).
No roles or descriptions are added, so their pages say 'not provided yet' until an administrator fills them in.
Departments a company already has (same web address) are left as they are."""
from django.db import migrations

DEPARTMENTS = [
    # (slug, name, icon, colour)
    ('finance', 'Finance Department', 'coins', 'blue'),
    ('marketing', 'Marketing Department', 'megaphone', 'purple'),
    ('hr', 'HR Department', 'people', 'orange'),
    ('sales', 'Sales Department', 'chart', 'green'),
    ('warehouse-operation', 'Warehouse Operation', 'box', 'teal'),
    ('trades', 'Trades Department', 'wrench', 'navy'),
]
OTHER_COMPANIES = ['farmer-joe', 'taula', 'burger-bills', 'tanumapua-farm']


def seed(apps, schema_editor):
    Company = apps.get_model('career_connect', 'Company')
    Department = apps.get_model('career_connect', 'Department')
    for company in Company.objects.filter(slug__in=OTHER_COMPANIES):
        for order, (slug, name, symbol, colour) in enumerate(DEPARTMENTS, start=1):
            Department.objects.get_or_create(company=company, slug=slug, defaults={
                'name': name, 'symbol': symbol, 'colour': colour, 'order': order})


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0007_company_background'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
