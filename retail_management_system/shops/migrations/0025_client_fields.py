from django.db import migrations


class Migration(migrations.Migration):
    """Owner becomes Contact Person, keeping everyone's existing value."""

    dependencies = [
        ('shops', '0024_promotion_details_prizes'),
    ]

    operations = [
        migrations.RenameField(model_name='shop', old_name='owner', new_name='contact_person'),
    ]
