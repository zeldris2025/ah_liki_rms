import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0035_access_level_groups'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='salesrep',
            name='user',
            field=models.OneToOneField(blank=True, help_text='Their login. Unless they’re a Manager, Corporate Sales then shows only their own stream, plus every rep’s % of this month’s target.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sales_rep', to=settings.AUTH_USER_MODEL),
        ),
    ]
