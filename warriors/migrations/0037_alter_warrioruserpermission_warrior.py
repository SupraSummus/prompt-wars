# Generated by Django 4.2.16 on 2024-09-29 10:53

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0036_remove_battle_result_1_2_remove_battle_result_2_1'),
    ]

    operations = [
        migrations.AlterField(
            model_name='warrioruserpermission',
            name='warrior',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='warriors.warrior'),
        ),
    ]
