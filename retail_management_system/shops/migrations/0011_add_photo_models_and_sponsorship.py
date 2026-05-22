from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0010_business_island'),
    ]

    operations = [
        # Add 'created' to Shop
        migrations.AddField(
            model_name='shop',
            name='created',
            field=models.DateField(auto_now_add=True, null=True, blank=True),
        ),
        # ShopPhoto  (replaces ShopImage; old ShopImage rows stay until cleaned up)
        migrations.CreateModel(
            name='ShopPhoto',
            fields=[
                ('id',       models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image',    models.ImageField(upload_to='shops/%Y/%m/')),
                ('note',     models.CharField(blank=True, help_text='Optional label', max_length=300)),
                ('uploaded', models.DateTimeField(auto_now_add=True)),
                ('shop',     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='shops.shop')),
            ],
            options={'ordering': ['uploaded']},
        ),
        # BusinessPhoto
        migrations.CreateModel(
            name='BusinessPhoto',
            fields=[
                ('id',       models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image',    models.ImageField(upload_to='horecca/%Y/%m/')),
                ('note',     models.CharField(blank=True, help_text='Optional label', max_length=300)),
                ('uploaded', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='shops.business')),
            ],
            options={'ordering': ['uploaded']},
        ),
        # Sponsorship
        migrations.CreateModel(
            name='Sponsorship',
            fields=[
                ('id',       models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer', models.CharField(max_length=200)),
                ('type',     models.CharField(choices=[('Signage','Signage'),('Cooler','Cooler'),('Event','Event'),('Vehicle','Vehicle'),('Uniform','Uniform'),('Digital','Digital'),('Other','Other')], default='Signage', max_length=20)),
                ('value',    models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('status',   models.CharField(choices=[('Active','Active'),('Expired','Expired'),('Pending','Pending')], default='Active', max_length=20)),
                ('start',    models.DateField(blank=True, null=True)),
                ('end',      models.DateField(blank=True, null=True)),
                ('notes',    models.TextField(blank=True)),
                ('created',  models.DateField(auto_now_add=True, null=True)),
            ],
            options={'ordering': ['-id']},
        ),
        # SponsorshipPhoto
        migrations.CreateModel(
            name='SponsorshipPhoto',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image',       models.ImageField(upload_to='sponsorships/%Y/%m/')),
                ('note',        models.CharField(blank=True, help_text='Optional label', max_length=300)),
                ('uploaded',    models.DateTimeField(auto_now_add=True)),
                ('sponsorship', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='shops.sponsorship')),
            ],
            options={'ordering': ['uploaded']},
        ),
        # Remove old Business.picture and Business.business_license fields
        migrations.RemoveField(model_name='business', name='picture'),
        migrations.RemoveField(model_name='business', name='business_license'),
        # Remove old Shop.business_license
        migrations.RemoveField(model_name='shop', name='business_license'),
    ]
