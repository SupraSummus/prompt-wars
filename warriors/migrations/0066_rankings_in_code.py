import uuid

import django.contrib.postgres.fields
import django.db.models.deletion
import django.db.models.functions.math
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


# Where arenas overlap, the one bound to a site wins, then an enabled one, then by name;
# that order picks the rating a warrior keeps in each ranking and the stats each ranking keeps.
ARENA_PREFERENCE = "(a.site_id IS NULL), (NOT a.enabled), a.name"
RANKING_OF_ALGORITHM = "CASE a.score_algorithm WHEN 'lcs' THEN 'lcs' WHEN 'embeddings' THEN 'semantic' END"

COPY_SQL = [
    # Every per-arena page id, so its URL keeps leading to the warrior.
    """
    INSERT INTO warriors_legacywarriorarena (id, warrior_id)
    SELECT id, warrior_id FROM warriors_warriorarena
    """,
    # One rating per (warrior, ranking), from the preferred arena of that algorithm.
    # The ratings were fit per model; `refit_ratings` refits them over every model's battles.
    f"""
    INSERT INTO warriors_warriorrating (
        id, warrior_id, ranking,
        rating, rating_playstyle, rating_fit_loss, rating_error, rating_updated_at,
        games_played
    )
    SELECT DISTINCT ON (wa.warrior_id, {RANKING_OF_ALGORITHM})
        wa.id, wa.warrior_id, {RANKING_OF_ALGORITHM},
        wa.rating, wa.rating_playstyle, wa.rating_fit_loss, wa.rating_error, wa.rating_updated_at,
        wa.games_played
    FROM warriors_warriorarena wa
    JOIN warriors_arena a ON a.id = wa.arena_id
    ORDER BY wa.warrior_id, {RANKING_OF_ALGORITHM}, {ARENA_PREFERENCE}
    """,
    # A warrior in any arena was entered for the ladder; its soonest clock carries over.
    """
    UPDATE warriors_warrior w
    SET next_battle_schedule = clock.next_battle_schedule
    FROM (
        SELECT warrior_id, min(next_battle_schedule) AS next_battle_schedule
        FROM warriors_warriorarena
        GROUP BY warrior_id
    ) clock
    WHERE clock.warrior_id = w.id
    """,
    # Every ranking ranks every ladder warrior, so one that was in no arena of an algorithm
    # starts that ranking unrated, as a newly submitted prompt does (`WarriorCreateForm.save`).
    """
    INSERT INTO warriors_warriorrating (
        id, warrior_id, ranking,
        rating, rating_playstyle, rating_fit_loss, rating_error, rating_updated_at,
        games_played
    )
    SELECT gen_random_uuid(), w.id, ranking.key, 0, '{}', 0, 0, now(), 0
    FROM warriors_warrior w
    CROSS JOIN (VALUES ('lcs'), ('semantic')) AS ranking (key)
    WHERE w.next_battle_schedule IS NOT NULL
    ON CONFLICT (warrior_id, ranking) DO NOTHING
    """,
    # Each ranking's history, from the preferred arena of its algorithm.
    f"""
    INSERT INTO warriors_rankingstats (
        id, date, ranking, warrior_count, battle_count, rating_quantiles
    )
    SELECT s.id, s.date, {RANKING_OF_ALGORITHM}, s.warrior_count, s.battle_count, s.rating_quantiles
    FROM warriors_arenastats s
    JOIN warriors_arena a ON a.id = s.arena_id
    WHERE a.id IN (
        SELECT DISTINCT ON (a.score_algorithm) a.id
        FROM warriors_arena a
        ORDER BY a.score_algorithm, {ARENA_PREFERENCE}
    )
    """,
]


class Migration(migrations.Migration):

    dependencies = [
        ('django_goals', '0011_goalpickup'),
        ('warriors', '0065_battle_rated'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Every step here is quick at production size (well under a second in all),
        # but taking a table's ACCESS EXCLUSIVE lock waits for every open transaction on it,
        # a worker's included, which holds its read locks through an LLM call with no timeout,
        # and every query after it queues behind the wait.
        # A stall of tens of seconds is acceptable; past that the whole migration rolls back,
        # to be retried, instead of stalling the site for as long as the slowest call.
        migrations.RunSQL("SET LOCAL lock_timeout = '20s'", reverse_sql=migrations.RunSQL.noop),
        migrations.RemoveField(
            model_name='arena',
            name='llm',
        ),
        migrations.RemoveField(
            model_name='battle',
            name='arena',
        ),
        migrations.CreateModel(
            name='LegacyWarriorArena',
            fields=[
                (
                    'id',
                    models.UUIDField(editable=False, primary_key=True, serialize=False),
                ),
            ],
        ),
        migrations.CreateModel(
            name='RankingStats',
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
                    'date',
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
                (
                    'ranking',
                    models.CharField(
                        choices=[
                            ('lcs', 'LCS ladder'),
                            ('semantic', 'Semantic ladder'),
                        ],
                        max_length=20,
                    ),
                ),
                ('warrior_count', models.PositiveIntegerField()),
                ('battle_count', models.PositiveIntegerField()),
                (
                    'rating_quantiles',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(),
                        help_text='i-th element is the rating of the i-th percentile',
                        size=101,
                    ),
                ),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
        migrations.CreateModel(
            name='WarriorRating',
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
                    'ranking',
                    models.CharField(
                        choices=[
                            ('lcs', 'LCS ladder'),
                            ('semantic', 'Semantic ladder'),
                        ],
                        max_length=20,
                    ),
                ),
                ('rating', models.FloatField(default=0.0)),
                (
                    'rating_playstyle',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(), default=list, size=2
                    ),
                ),
                ('rating_fit_loss', models.FloatField(default=0.0)),
                ('rating_error', models.FloatField(default=0.0)),
                (
                    'rating_updated_at',
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ('games_played', models.PositiveIntegerField(default=0)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.AddField(
            model_name='warrior',
            name='next_battle_schedule',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='warrior',
            index=models.Index(
                condition=models.Q(('moderation_passed', True)),
                fields=['next_battle_schedule'],
                name='warrior_next_battle_index',
            ),
        ),
        migrations.AddField(
            model_name='legacywarriorarena',
            name='warrior',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                to='warriors.warrior',
            ),
        ),
        migrations.AddField(
            model_name='warriorrating',
            name='warrior',
            field=models.ForeignKey(
                db_index=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='ratings',
                to='warriors.warrior',
            ),
        ),
        migrations.AddIndex(
            model_name='warriorrating',
            index=models.Index(
                fields=['ranking', 'rating'], name='ranking_rating_index'
            ),
        ),
        migrations.AddIndex(
            model_name='warriorrating',
            index=models.Index(
                django.db.models.functions.math.Abs('rating_error'),
                name='warrior_rating_error_index',
            ),
        ),
        migrations.AddConstraint(
            model_name='warriorrating',
            constraint=models.UniqueConstraint(
                fields=('warrior', 'ranking'), name='warrior_ranking_unique'
            ),
        ),
        # irreversible: the rows it drops a warrior's duplicates from cannot be split back
        migrations.RunSQL(COPY_SQL),
        migrations.DeleteModel(
            name='ArenaStats',
        ),
        migrations.DeleteModel(
            name='WarriorArena',
        ),
        migrations.DeleteModel(
            name='Arena',
        ),
    ]
