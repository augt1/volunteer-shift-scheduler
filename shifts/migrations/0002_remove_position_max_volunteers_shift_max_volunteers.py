# Generated by Django 5.2 on 2025-04-23 14:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shifts', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='position',
            name='max_volunteers',
        ),
        migrations.AddField(
            model_name='shift',
            name='max_volunteers',
            field=models.IntegerField(default=1, help_text='Maximum number of volunteers for this position'),
        ),
    ]
