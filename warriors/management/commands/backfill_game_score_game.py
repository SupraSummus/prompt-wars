"""
Point older `GameScore` rows at the game row they score.

`get_or_create_game_score` names the game on every row it writes,
but the rows that predate the column carry only (battle, direction).
The game row is what they identify — the pair maps to it one-to-one —
so this is a re-keying, not a repair: no value is chosen, only looked up.

Set-based, batched by page range, each batch its own transaction,
so it holds no long locks and can be interrupted and rerun.
Batching by physical position rather than by score id is the point:
the primary key is a random uuid,
so a batch taken in id order scatters its rows over the whole table
and over every index the write maintains, a page fetch each,
and hauls every id through the client to name them.
A page range names rows by where they already sit,
and is wide enough that the planner hashes the games and battles once
instead of probing per row — measured 5x on a million unlinked scores.
`backfill_game_input_sha256` keeps the id-keyed shape
because the rows it repairs number in the tens.

Each pass reads the page count again,
because the rows it writes extend the table as it goes.
Its own writes only ever move a row it has already linked,
but a concurrent write to a legacy score can move an unlinked one
behind the cursor — so run it until it reports nothing left.

Both directions go in one statement —
the CASE that says which end of the battle a direction starts from
costs less than a second pass over the page range.

Delete this command once a production run reports nothing left to link:
the not-null migration that follows leaves it nothing to find.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from ...score import GameScore


LINK_SQL = """
    UPDATE warriors_gamescore s
    SET game_id = g.id
    FROM warriors_battle b, warriors_game g
    WHERE s.ctid >= %(start)s::tid
      AND s.ctid < %(end)s::tid
      AND s.game_id IS NULL
      AND b.id = s.battle_id
      AND g.battle_id = b.id
      AND g.warrior_1_id = CASE s.direction
          WHEN '1_2' THEN b.warrior_1_id
          WHEN '2_1' THEN b.warrior_2_id
      END
"""
PAGE_COUNT_SQL = """
    SELECT pg_relation_size('warriors_gamescore')
         / current_setting('block_size')::bigint
"""


class Command(BaseCommand):
    help = 'Link game scores to the game row they score'

    def add_arguments(self, parser):
        parser.add_argument('--batch-pages', type=int, default=2000)

    def handle(self, *args, batch_pages, **options):
        if batch_pages < 1:
            # a zero-page batch never advances the cursor
            raise CommandError('--batch-pages must be at least 1')
        block = 0
        linked = 0
        while True:
            pages = self.page_count()
            if block >= pages:
                break
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(LINK_SQL, {
                    'start': f'({block},0)',
                    'end': f'({block + batch_pages},0)',
                })
                linked += cursor.rowcount
            block = min(block + batch_pages, pages)
            self.stdout.write(f'pages {block}/{pages}, linked {linked}')
        unlinked = GameScore.objects.filter(game=None).count()
        # what is left is a score whose battle direction has no game row:
        # a broken invariant for verify_games to report, not a gap to fill
        self.stdout.write(f'done: linked {linked}, {unlinked} still unlinked')

    def page_count(self):
        with connection.cursor() as cursor:
            cursor.execute(PAGE_COUNT_SQL)
            (pages,) = cursor.fetchone()
        return pages
