# Generated by Django 4.2.16 on 2024-09-26 14:34

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0034_remove_warriorarena_body_sha_256_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TextUnit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('sha_256', models.BinaryField(max_length=32, unique=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.AddConstraint(
            model_name='textunit',
            constraint=models.CheckConstraint(check=models.Q(('sha_256', models.Func(models.Func(models.F('content'), models.Value('utf-8'), function='convert_to'), function='sha256'))), name='text_unit_sha_256'),
        ),
        migrations.AddField(
            model_name='battle',
            name='text_unit_1_2',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='warriors.textunit'),
        ),
        migrations.AddField(
            model_name='battle',
            name='text_unit_2_1',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='warriors.textunit'),
        ),
    ]
