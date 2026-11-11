import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0017_application_stage'),
    ]

    operations = [
        migrations.CreateModel(
            name='StaffTurnover',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week', models.DateField(help_text='The Monday the week starts on. A week belongs to the month its '
                                                    'Monday is in.')),
                ('leavers', models.PositiveIntegerField(verbose_name='employees who left')),
                ('employees', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)],
                                                          verbose_name='number of employees')),
                ('rate', models.DecimalField(decimal_places=2, editable=False, max_digits=6,
                                             help_text='Employees who left ÷ number of employees × 100.',
                                             verbose_name='turnover %')),
                ('note', models.CharField(blank=True, max_length=200)),
                ('updated_by', models.CharField(blank=True, max_length=150)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='turnover',
                                              to='career_connect.company')),
            ],
            options={
                'verbose_name': 'staff turnover',
                'verbose_name_plural': 'staff turnover',
                'ordering': ('-week', 'company__order'),
                'constraints': [models.UniqueConstraint(fields=('company', 'week'),
                                                        name='one_turnover_per_company_week')],
            },
        ),
    ]
