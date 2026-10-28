from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0005_companies'),
    ]

    operations = [
        migrations.AlterField(
            model_name='department',
            name='company',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='departments',
                                    to='career_connect.company'),
        ),
        migrations.AlterField(
            model_name='department',
            name='slug',
            field=models.SlugField(help_text='Used in the web address, e.g. "finance"; unique within the company.', max_length=80),
        ),
        migrations.AlterModelOptions(
            name='department',
            options={'ordering': ('company__order', 'order', 'name')},
        ),
        migrations.AlterModelOptions(
            name='role',
            options={'ordering': ('department__company__order', 'department__order', 'order', 'title')},
        ),
        migrations.AddConstraint(
            model_name='department',
            constraint=models.UniqueConstraint(fields=('company', 'slug'), name='career_department_unique_slug'),
        ),
    ]
