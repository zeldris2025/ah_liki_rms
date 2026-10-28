"""Department background photos are uploaded on the department itself (shown faded, 50% by default), instead of
being picked from the company photo gallery. Any photo already picked is kept: its file becomes the background."""
import django.core.validators
from django.db import migrations, models

import career_connect.models


def copy_picked_photos(apps, schema_editor):
    Department = apps.get_model('career_connect', 'Department')
    for dept in Department.objects.exclude(image=None).select_related('image'):
        dept.background = dept.image.image.name
        dept.save(update_fields=['background'])


class Migration(migrations.Migration):

    dependencies = [
        ('career_connect', '0003_design_refresh'),
    ]

    operations = [
        migrations.AddField(
            model_name='department',
            name='background',
            field=models.ImageField(
                blank=True, upload_to='career_connect/departments/', verbose_name='background photo',
                help_text='Optional. Shown faded behind the department card and page heading (JPG, PNG or WebP, under 8 MB).',
                validators=[django.core.validators.FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']),
                            career_connect.models._photo_size]),
        ),
        migrations.AddField(
            model_name='department',
            name='background_opacity',
            field=models.PositiveSmallIntegerField(
                default=50, verbose_name='photo strength (%)',
                help_text='How strongly the photo shows over the department colour: 50 = half faded (recommended).',
                validators=[django.core.validators.MinValueValidator(10), django.core.validators.MaxValueValidator(90)]),
        ),
        migrations.RunPython(copy_picked_photos, migrations.RunPython.noop),
        migrations.RemoveField(model_name='department', name='image'),
    ]
