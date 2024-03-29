# Generated by Django 4.2.10 on 2024-02-25 00:43

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('warriors', '0016_remove_warrior_rating_index_warrior_rating_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='Arena',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('name', models.CharField(max_length=40, unique=True)),
                ('prompt', models.TextField(max_length=1000, blank=True)),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.AddField(
            model_name='battle',
            name='arena',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='warriors.arena',
            ),
        ),
        migrations.AddField(
            model_name='warrior',
            name='arena',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='warriors.arena',
            ),
        ),
    ]
