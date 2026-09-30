from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0023_alter_business_id_alter_businessphoto_id_and_more'),
    ]

    operations = [
        migrations.RenameField(model_name='promotion', old_name='description', new_name='details'),
        migrations.AddField(
            model_name='promotion',
            name='prizes',
            field=models.TextField(blank=True, help_text='One prize per line, e.g. 1st — WST 500 voucher'),
        ),
        migrations.AlterField(
            model_name='promotion',
            name='name',
            field=models.CharField(max_length=255, verbose_name='Promotion name'),
        ),
        # Status is now worked out from the start and end dates
        migrations.RemoveField(model_name='promotion', name='status'),
        migrations.RemoveField(model_name='promotion', name='promotion_type'),
    ]
