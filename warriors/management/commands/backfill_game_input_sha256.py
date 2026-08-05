"""
Copy `Battle.input_sha256_*` onto the game rows that lack it.

The root-level `backfill_sha.py` computes the sha
for battles resolved before those columns existed
and writes only the battle side,
so those battles carry the value on one side of the mirror.
`verify_games` reports them as `blank input_sha256`; this fills them in.
The battle holds the only copy, so filling it in loses nothing.

Set-based, batched by game id, each batch its own transaction,
so it holds no long locks and can be interrupted and rerun.
The two directions are separate statements:
one statement would need a CASE over the swapped warrior pair
in both the projection and the guard against writing null over null.

Delete this command once a production run leaves nothing to fill —
it is a one-time repair,
and it goes with the columns it copies from
in the column-drop step of `docs/game-migration.md`.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from ...battles import DBGame


FILL_SQL = """
    UPDATE warriors_game g
    SET input_sha256 = b.{column}
    FROM warriors_battle b
    WHERE g.id = ANY(%(ids)s)
      AND g.battle_id = b.id
      AND g.warrior_1_id = b.{first}
      AND g.input_sha256 IS NULL
      AND b.{column} IS NOT NULL
"""
DIRECTIONS = (
    ('input_sha256_1_2', 'warrior_1_id'),
    ('input_sha256_2_1', 'warrior_2_id'),
)


class Command(BaseCommand):
    help = 'Fill game rows missing the input sha their battle has'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=10000)

    def handle(self, *args, batch_size, **options):
        scanned = 0
        filled = 0
        last_id = None
        while True:
            games = DBGame.objects.filter(input_sha256=None).order_by('id')
            if last_id is not None:
                games = games.filter(id__gt=last_id)
            ids = list(games.values_list('id', flat=True)[:batch_size])
            if not ids:
                break
            last_id = ids[-1]
            scanned += len(ids)
            with transaction.atomic(), connection.cursor() as cursor:
                for column, first in DIRECTIONS:
                    cursor.execute(
                        FILL_SQL.format(column=column, first=first),
                        {'ids': ids},
                    )
                    filled += cursor.rowcount
            self.stdout.write(f'scanned {scanned}, filled {filled}')
        blank = DBGame.objects.filter(input_sha256=None).count()
        # what is left is a direction whose battle has no sha either:
        # unresolved, or a gap for verify_games to report
        self.stdout.write(f'done: filled {filled}, {blank} still blank')
