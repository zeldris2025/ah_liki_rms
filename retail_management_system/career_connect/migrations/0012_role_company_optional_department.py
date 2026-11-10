"""Roles belong to a company and only optionally to a department, so companies without departments can post them.
Existing roles get the company of their department."""
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Q, Subquery


def fill_company(apps, schema_editor):
    Role, Department = apps.get_model('career_connect', 'Role'), apps.get_model('career_connect', 'Department')
    Role.objects.update(company=Subquery(Department.objects.filter(pk=OuterRef('department')).values('company')[:1]))


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0011_role_expires_on'),
    ]

    operations = [
        migrations.AddField(
            model_name='role',
            name='company',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='roles',
                                    to='career_connect.company'),
        ),
        migrations.RunPython(fill_company, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='role',
            name='company',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='roles',
                                    to='career_connect.company'),
        ),
        migrations.AlterField(
            model_name='role',
            name='department',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='roles',
                to='career_connect.department',
                help_text='Optional. Leave empty for a company without departments: the role is listed on the company page.'),
        ),
        migrations.AlterField(
            model_name='role',
            name='slug',
            field=models.SlugField(max_length=80, help_text='Used in the web address; unique within the department '
                                                            '(or within the company, for roles without a department).'),
        ),
        migrations.AlterModelOptions(
            name='role',
            options={'ordering': ('company__order', 'department__order', 'order', 'title'),
                     'permissions': [('manage_vacancies', 'Can post and update vacancies on the HR vacancies page')]},
        ),
        migrations.AddConstraint(
            model_name='role',
            constraint=models.UniqueConstraint(condition=Q(department__isnull=True), fields=('company', 'slug'),
                                               name='career_company_role_unique_slug'),
        ),
    ]
