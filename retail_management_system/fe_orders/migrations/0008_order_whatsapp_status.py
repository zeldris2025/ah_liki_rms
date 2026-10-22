from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fe_orders', '0007_email_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='whatsapp_status',
            field=models.CharField(blank=True, help_text='Result of the WhatsApp (WAHA) group notification', max_length=120),
        ),
    ]
