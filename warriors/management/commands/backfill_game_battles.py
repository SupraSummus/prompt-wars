"""
Link legacy DBGame rows to their Battle
by the (llm, warrior pair, scheduled_at) match;
docs/game-migration.md, step 1, owns why that triple is acceptable here
and what follows once the final report shows zero unlinked rows.

Runs in batches, each its own transaction,
so it holds no long locks and can be interrupted and rerun;
already-linked rows are never touched.
The two directions are matched by separate equality-only updates:
a single update with an OR over the swapped warrior pair
defeats the planner (no hash join) and degrades to
a per-row nested loop over the battles table.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from ...battles import DBGame


MATCH_SQL = """
    UPDATE warriors_game g
    SET battle_id = b.id
    FROM warriors_battle b
    WHERE g.id = ANY(%(ids)s)
      AND g.battle_id IS NULL
      AND b.llm = g.llm
      AND b.scheduled_at = g.scheduled_at
      AND b.warrior_1_id = g.{first}
      AND b.warrior_2_id = g.{second}
"""


class Command(BaseCommand):
    help = 'Link legacy game rows to their battle'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=10000)

    def handle(self, *args, batch_size, **options):
        last_id = None
        scanned = 0
        linked = 0
        while True:
            games = DBGame.objects.filter(battle=None).order_by('id')
            if last_id is not None:
                games = games.filter(id__gt=last_id)
            ids = list(games.values_list('id', flat=True)[:batch_size])
            if not ids:
                break
            last_id = ids[-1]
            scanned += len(ids)
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    MATCH_SQL.format(first='warrior_1_id', second='warrior_2_id'),
                    {'ids': ids},
                )
                linked += cursor.rowcount
                cursor.execute(
                    MATCH_SQL.format(first='warrior_2_id', second='warrior_1_id'),
                    {'ids': ids},
                )
                linked += cursor.rowcount
            self.stdout.write(f'scanned {scanned}, linked {linked}')
        unlinked = DBGame.objects.filter(battle=None).count()
        self.stdout.write(f'done: linked {linked}, {unlinked} left unlinked')
