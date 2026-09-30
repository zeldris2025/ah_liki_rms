from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fe_orders', '0005_product_no_cost_vat'),
    ]

    operations = [
        # WhatsApp notifications were replaced by Telegram; old results are kept under the new name
        migrations.RenameField(model_name='order', old_name='whatsapp_status', new_name='telegram_status'),
        migrations.AlterField(
            model_name='order',
            name='telegram_status',
            field=models.CharField(blank=True, help_text='Result of the Telegram group notification', max_length=120),
        ),
    ]
