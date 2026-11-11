from django.db import migrations, models


def reviewed_to_stage(apps, schema_editor):
    apps.get_model('career_connect', 'ExpressionOfInterest').objects.filter(reviewed=True).update(stage='reviewed')


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0016_application_email_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='expressionofinterest',
            name='stage',
            field=models.CharField(choices=[('new', 'New'), ('reviewed', 'Reviewed'), ('interview', 'Interview'),
                                            ('offered', 'Offered'), ('hired', 'Hired'), ('unsuccessful', 'Unsuccessful')],
                                   db_index=True, default='new', max_length=20),
        ),
        migrations.AddField(
            model_name='expressionofinterest',
            name='interview_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='interview'),
        ),
        migrations.AddField(
            model_name='expressionofinterest',
            name='stage_changed_at',
            field=models.DateTimeField(blank=True, help_text='When the stage last changed, e.g. the hire date.', null=True),
        ),
        migrations.RunPython(reviewed_to_stage, migrations.RunPython.noop),
    ]
