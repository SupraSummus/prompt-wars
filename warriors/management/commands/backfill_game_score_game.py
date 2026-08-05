"""
Point older `GameScore` rows at the game row they score.

`get_or_create_game_score` names the game on every row it writes,
but the rows that predate the column carry only (battle, direction).
The game row is what they identify — the pair maps to it one-to-one —
so this is a re-keying, not a repair: no value is chosen, only looked up.

Set-based, batched by score id, each batch its own transaction,
so it holds no long locks and can be interrupted and rerun.
The two directions are separate statements:
one statement would need a CASE over the swapped warrior pair
to say which end of the battle the direction starts from.

Delete this command once a production run reports nothing left to link:
the not-null migration that follows leaves it nothing to find.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from ...score import GameScore


LINK_SQL = """
    UPDATE warriors_gamescore s
    SET game_id = g.id
    FROM warriors_battle b, warriors_game g
    WHERE s.id = ANY(%(ids)s)
      AND s.game_id IS NULL
      AND s.direction = %(direction)s
      AND b.id = s.battle_id
      AND g.battle_id = b.id
      AND g.warrior_1_id = b.{first}
"""
DIRECTIONS = (
    ('1_2', 'warrior_1_id'),
    ('2_1', 'warrior_2_id'),
)


class Command(BaseCommand):
    help = 'Link game scores to the game row they score'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=10000)

    def handle(self, *args, batch_size, **options):
        scanned = 0
        linked = 0
        last_id = None
        while True:
            scores = GameScore.objects.filter(game=None).order_by('id')
            if last_id is not None:
                scores = scores.filter(id__gt=last_id)
            ids = list(scores.values_list('id', flat=True)[:batch_size])
            if not ids:
                break
            last_id = ids[-1]
            scanned += len(ids)
            with transaction.atomic(), connection.cursor() as cursor:
                for direction, first in DIRECTIONS:
                    cursor.execute(
                        LINK_SQL.format(first=first),
                        {'ids': ids, 'direction': direction},
                    )
                    linked += cursor.rowcount
            self.stdout.write(f'scanned {scanned}, linked {linked}')
        unlinked = GameScore.objects.filter(game=None).count()
        # what is left is a score whose battle direction has no game row:
        # a broken invariant for verify_games to report, not a gap to fill
        self.stdout.write(f'done: linked {linked}, {unlinked} still unlinked')
