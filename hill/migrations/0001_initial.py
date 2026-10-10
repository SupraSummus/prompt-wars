import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('warriors', '0065_battle_rated'),
    ]

    operations = [
        # The foreign keys into the warrior and battle tables
        # lock those tables against writes while they are added,
        # behind every battle-resolving transaction that holds them;
        # failing fast fails the deploy, which can be retried,
        # rather than stalling the site's writes queued behind the lock.
        migrations.RunSQL(
            "SET LOCAL lock_timeout = '5s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name='Hill',
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
                ('enabled', models.BooleanField(default=False)),
                (
                    'llm',
                    models.CharField(
                        choices=[
                            ('google-gemini', 'Google Gemini'),
                            ('claude-3-haiku', 'Anthropic Claude'),
                        ],
                        default='google-gemini',
                        help_text='Copied into each new round, so a change takes effect at the next handover.',
                        max_length=20,
                    ),
                ),
                (
                    'daily_attempt_limit',
                    models.PositiveIntegerField(
                        default=1000,
                        help_text="Attacks per round: the cap on the hill's daily LLM spend.",
                    ),
                ),
                (
                    'max_pending',
                    models.PositiveSmallIntegerField(
                        default=10,
                        help_text='Attacks in battle at once, across rounds, before new ones are refused. Lower it to hand the worker back to the ladder during a spike.',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='HillAttempt',
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
                ('identity', models.CharField(max_length=64)),
                ('display_name', models.CharField(blank=True, max_length=40)),
                ('display_author', models.CharField(blank=True, max_length=40)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                (
                    'state',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('scored', 'Scored'),
                            ('failed', 'Failed'),
                            ('flagged', 'Flagged by moderation'),
                            ('void', 'Void'),
                        ],
                        default='pending',
                        max_length=10,
                    ),
                ),
                (
                    'late',
                    models.BooleanField(
                        default=False,
                        help_text='Still in battle when its round closed: shown to its author, never counted.',
                    ),
                ),
                ('score', models.FloatField(blank=True, null=True)),
                ('survived_chars', models.PositiveIntegerField(blank=True, null=True)),
                (
                    'crown_block',
                    models.CharField(
                        blank=True,
                        choices=[
                            ('', 'None'),
                            ('too_little_survived', 'Too little survived'),
                            ('repetitive_reply', 'Repetitive reply'),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    'output_moderation_passed',
                    models.BooleanField(
                        blank=True,
                        help_text="Moderation of the battle's replies, run once the attempt takes the hill.",
                        null=True,
                    ),
                ),
                (
                    'battle',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='hill_attempt',
                        to='warriors.battle',
                    ),
                ),
                (
                    'warrior',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='hill_attempts',
                        to='warriors.warrior',
                    ),
                ),
            ],
            options={
                'ordering': ('created_at',),
            },
        ),
        migrations.CreateModel(
            name='Round',
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
                ('number', models.PositiveIntegerField()),
                ('starts_at', models.DateTimeField()),
                ('ends_at', models.DateTimeField()),
                (
                    'llm',
                    models.CharField(
                        choices=[
                            ('openai-gpt', 'OpenAI GPT'),
                            ('claude-3-haiku', 'Anthropic Claude'),
                            ('google-gemini', 'Google Gemini'),
                        ],
                        max_length=20,
                    ),
                ),
                ('boss_name', models.CharField(blank=True, max_length=40)),
                ('boss_author', models.CharField(blank=True, max_length=40)),
                (
                    'reign_round',
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text='Consecutive rounds this boss has held, counting this one.',
                    ),
                ),
                (
                    'boss_reason',
                    models.CharField(
                        choices=[
                            ('owner', 'Crowned by the owner'),
                            ('broke', 'Broke the hill'),
                            ('inherited', 'Inherited the hill'),
                            ('house', 'House boss'),
                            ('held', 'Held the hill'),
                        ],
                        max_length=10,
                    ),
                ),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                (
                    'boss',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='+',
                        to='warriors.warrior',
                    ),
                ),
                (
                    'boss_attempt',
                    models.ForeignKey(
                        blank=True,
                        help_text='The attack that put this boss on the hill; none for owner and house bosses.',
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='+',
                        to='hill.hillattempt',
                    ),
                ),
                (
                    'hill',
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='rounds',
                        to='hill.hill',
                    ),
                ),
            ],
            options={
                'ordering': ('-number',),
            },
        ),
        migrations.AddField(
            model_name='hillattempt',
            name='hill_round',
            field=models.ForeignKey(
                db_index=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='attempts',
                to='hill.round',
            ),
        ),
        migrations.CreateModel(
            name='HouseBoss',
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
                ('name', models.CharField(blank=True, max_length=40)),
                ('author', models.CharField(blank=True, max_length=40)),
                (
                    'hill',
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        to='hill.hill',
                    ),
                ),
                (
                    'warrior',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='+',
                        to='warriors.warrior',
                    ),
                ),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(
                        fields=('hill', 'warrior'), name='hill_house_boss_unique'
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='round',
            constraint=models.UniqueConstraint(
                fields=('hill', 'number'), name='hill_round_number_unique'
            ),
        ),
        migrations.AddConstraint(
            model_name='round',
            constraint=models.UniqueConstraint(
                condition=models.Q(('closed_at', None)),
                fields=('hill',),
                name='hill_one_open_round',
            ),
        ),
        migrations.AddIndex(
            model_name='hillattempt',
            index=models.Index(
                fields=['hill_round', 'identity'], name='hill_attempt_round_identity'
            ),
        ),
        migrations.AddIndex(
            model_name='hillattempt',
            index=models.Index(
                condition=models.Q(('state', 'pending')),
                fields=['created_at'],
                name='hill_attempt_pending',
            ),
        ),
        migrations.AddConstraint(
            model_name='hillattempt',
            constraint=models.UniqueConstraint(
                condition=models.Q(('state', 'void'), _negated=True),
                fields=('hill_round', 'warrior'),
                name='hill_attempt_live_unique',
            ),
        ),
    ]
