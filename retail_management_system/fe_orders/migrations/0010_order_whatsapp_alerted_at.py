from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fe_orders', '0009_order_whatsapp_retry_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='whatsapp_alerted_at',
            field=models.DateTimeField(blank=True, null=True, help_text='When staff were emailed that the WhatsApp message failed'),
        ),
    ]
