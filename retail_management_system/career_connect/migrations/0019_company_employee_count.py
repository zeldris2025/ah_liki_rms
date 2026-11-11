import django.core.validators
from django.db import migrations, models


def from_latest_week(apps, schema_editor):
    """Start each company's number of employees from its latest week of turnover, if it has one."""
    Company = apps.get_model('career_connect', 'Company')
    StaffTurnover = apps.get_model('career_connect', 'StaffTurnover')
    for company in Company.objects.all():
        last = StaffTurnover.objects.filter(company=company).order_by('-week').first()
        if last:
            company.employee_count = last.employees
            company.save(update_fields=['employee_count'])


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0018_staff_turnover'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='employee_count',
            field=models.PositiveIntegerField(
                blank=True, help_text='Used for the staff turnover %. It stays the same until HR change it.', null=True,
                validators=[django.core.validators.MinValueValidator(1)], verbose_name='number of employees'),
        ),
        migrations.RunPython(from_latest_week, migrations.RunPython.noop),
    ]
