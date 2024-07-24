# Generated by Django 4.2.14 on 2024-07-23 15:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0027_remove_warrior_rating_error_non_negative_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='warrior',
            name='public_battle_results',
            field=models.BooleanField(default=False, help_text='Indicates whether battle results should be public for this warrior.'),
        ),
        migrations.AddField(
            model_name='warrioruserpermission',
            name='public_battle_results',
            field=models.BooleanField(default=False),
        ),
    ]
