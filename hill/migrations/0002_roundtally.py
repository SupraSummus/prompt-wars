import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hill', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoundTally',
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
                    'kind',
                    models.CharField(
                        choices=[
                            ('share_pressed', 'Share pressed'),
                            ('new_via_share', 'New player through a shared link'),
                        ],
                        max_length=20,
                    ),
                ),
                ('count', models.PositiveIntegerField()),
                (
                    'hill_round',
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='tallies',
                        to='hill.round',
                    ),
                ),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(
                        fields=('hill_round', 'kind'), name='hill_round_tally_unique'
                    )
                ],
            },
        ),
    ]
