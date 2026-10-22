from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fe_orders', '0008_order_whatsapp_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='whatsapp_retry_at',
            field=models.DateTimeField(blank=True, null=True, help_text='When to try the WhatsApp message again if it hasn’t gone yet'),
        ),
    ]
