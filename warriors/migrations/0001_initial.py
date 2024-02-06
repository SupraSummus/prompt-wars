# Generated by Django 4.2.9 on 2024-02-06 00:31

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Warrior',
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
                ('body', models.TextField(max_length=1000)),
                ('body_sha_256', models.BinaryField(max_length=32, unique=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('name', models.CharField(blank=True, max_length=100)),
                ('author', models.CharField(blank=True, max_length=100)),
                ('rating', models.FloatField(db_index=True, default=0.0)),
                (
                    'next_battle_schedule',
                    models.DateTimeField(db_index=None, default=None),
                ),
            ],
            options={
                'ordering': ('-rating',),
            },
        ),
        migrations.CreateModel(
            name='Battle',
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
                (
                    'scheduled_at',
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ('warrior_1_rating', models.FloatField()),
                ('warrior_2_rating', models.FloatField()),
                ('result_1_2', models.TextField(blank=True, max_length=1000)),
                ('llm_version_1_2', models.CharField(blank=True, max_length=100)),
                ('resolved_at_1_2', models.DateTimeField(blank=True, null=True)),
                ('result_2_1', models.TextField(blank=True, max_length=1000)),
                ('llm_version_2_1', models.CharField(blank=True, max_length=100)),
                ('resolved_at_2_1', models.DateTimeField(blank=True, null=True)),
                ('rating_transferred_at', models.DateTimeField(blank=True, null=True)),
                (
                    'warrior_1',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='warrior1',
                        to='warriors.warrior',
                    ),
                ),
                (
                    'warrior_2',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='warrior2',
                        to='warriors.warrior',
                    ),
                ),
            ],
            options={
                'ordering': ('-scheduled_at',),
            },
        ),
    ]
