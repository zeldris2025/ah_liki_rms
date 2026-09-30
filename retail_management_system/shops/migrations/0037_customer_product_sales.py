import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0036_sales_rep_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerProductSales',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_code', models.CharField(max_length=50)),
                ('product_name', models.CharField(max_length=255)),
                ('month', models.DateField(help_text='Stored as the first day of the month')),
                ('sales', models.DecimalField(decimal_places=2, max_digits=14)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_sales', to='shops.shop')),
            ],
            options={
                'verbose_name_plural': 'Customer product sales',
                'ordering': ['-month', '-sales'],
                'constraints': [models.UniqueConstraint(fields=('shop', 'product_code', 'month'), name='one_total_per_client_product_month')],
            },
        ),
    ]
