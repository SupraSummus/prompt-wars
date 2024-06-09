# Generated by Django 4.2.13 on 2024-06-09 22:06

import django.db.models.functions.math
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0026_warrior_rating_fit_loss'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='warrior',
            name='rating_error_non_negative',
        ),
        migrations.AlterField(
            model_name='warrior',
            name='rating_error',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddIndex(
            model_name='warrior',
            index=models.Index(django.db.models.functions.math.Abs('rating_error'), name='rating_error_index'),
        ),
    ]
