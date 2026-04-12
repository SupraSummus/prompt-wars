import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from pgvector.django import BitField

import guessing.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('embedding_explorer', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GuessingTarget',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('embedding', BitField(default=guessing.models._random_bits, length=2048)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Guess',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('target', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='guesses',
                    to='guessing.guessingtarget',
                )),
                ('query', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='guesses',
                    to='embedding_explorer.explorerquery',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='guesses',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='guess',
            constraint=models.UniqueConstraint(
                fields=['target', 'query', 'user'],
                name='guess_target_query_user_unique',
            ),
        ),
    ]
