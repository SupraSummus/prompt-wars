# Generated by Django 4.2.13 on 2024-06-09 15:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0025_warrior_rating_playstyle'),
    ]

    operations = [
        migrations.AddField(
            model_name='warrior',
            name='rating_fit_loss',
            field=models.FloatField(default=0.0),
        ),
    ]
