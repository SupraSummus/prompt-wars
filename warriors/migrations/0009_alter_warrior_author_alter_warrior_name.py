# Generated by Django 4.2.10 on 2024-02-13 00:12

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('warriors', '0008_battle_lcs_len_1_2_1_battle_lcs_len_1_2_2_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='warrior',
            name='author',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AlterField(
            model_name='warrior',
            name='name',
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
