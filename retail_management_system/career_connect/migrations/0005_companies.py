"""Companies in the Ah Liki Investment group, above departments. The existing departments (and their roles) belong
to Ah Liki Wholesale; the other companies start with no departments, so their pages say 'not provided yet'."""
import django.db.models.deletion
from django.db import migrations, models

COMPANIES = [
    # (slug, name, colour, icon)
    ('ah-liki-wholesale', 'Ah Liki Wholesale', 'blue', 'store'),
    ('farmer-joe', 'Farmer Joe', 'green', 'cart'),
    ('taula', 'Taula', 'purple', 'building'),
    ('burger-bills', 'Burger Bills', 'red', 'utensils'),
    ('tanumapua-farm', 'Tanumapua Farm', 'teal', 'leaf'),
]
GROUP = 'Career Connect Admin'
GROUP_PERMS = ['add_company', 'change_company', 'delete_company', 'view_company']


def seed(apps, schema_editor):
    from django.contrib.auth.management import create_permissions
    Company = apps.get_model('career_connect', 'Company')
    Department = apps.get_model('career_connect', 'Department')
    for order, (slug, name, colour, symbol) in enumerate(COMPANIES, start=1):
        Company.objects.get_or_create(slug=slug, defaults={'name': name, 'colour': colour, 'symbol': symbol,
                                                           'order': order})
    Department.objects.filter(company=None).update(company=Company.objects.get(slug='ah-liki-wholesale'))

    app_config = apps.get_app_config('career_connect')
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    group = Group.objects.filter(name=GROUP).first()
    if group:
        group.permissions.add(*Permission.objects.filter(content_type__app_label='career_connect',
                                                         codename__in=GROUP_PERMS))


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0004_department_background'),
    ]

    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('slug', models.SlugField(help_text='Used in the web address, e.g. "farmer-joe".', max_length=80, unique=True)),
                ('symbol', models.CharField(choices=[('store', 'Store (wholesale / retail)'), ('cart', 'Cart (supermarket)'), ('utensils', 'Utensils (food)'), ('leaf', 'Leaf (farm)'), ('building', 'Building')], default='building', max_length=20, verbose_name='icon')),
                ('colour', models.CharField(choices=[('blue', 'Blue'), ('purple', 'Purple'), ('orange', 'Orange'), ('green', 'Green'), ('teal', 'Teal'), ('navy', 'Navy'), ('red', 'Red')], default='navy', max_length=20)),
                ('description', models.TextField(blank=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('is_published', models.BooleanField(default=True)),
            ],
            options={'ordering': ('order', 'name'), 'verbose_name_plural': 'companies'},
        ),
        migrations.AddField(
            model_name='department',
            name='company',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='departments',
                                    to='career_connect.company'),
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
