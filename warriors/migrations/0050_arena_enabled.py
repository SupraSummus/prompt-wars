# Generated by Django 4.2.19 on 2025-02-21 19:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0049_arena_score_algorithm'),
    ]

    operations = [
        migrations.AddField(
            model_name='arena',
            name='enabled',
            field=models.BooleanField(default=True),
        ),
    ]
