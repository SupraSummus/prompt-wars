import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
from pgvector.django import BitField, VectorExtension


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('django_goals', '0001_initial'),
    ]

    operations = [
        VectorExtension(),
        migrations.CreateModel(
            name='ExplorerQuery',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('phrase', models.TextField(max_length=100)),
                ('phrase_sha_256', models.BinaryField(max_length=32, unique=True)),
                ('embedding', BitField(blank=True, length=2048, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('embedding_goal', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='django_goals.goal',
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(phrase_sha_256=models.Func(
                            models.Func(
                                models.F('phrase'),
                                models.Value('utf-8'),
                                function='convert_to',
                            ),
                            function='sha256',
                        )),
                        name='explorer_query_phrase_sha_256',
                    ),
                ],
            },
        ),
    ]
