"""
Copy a battle direction's result onto the game row that never got it.

Some game rows hold none of the result their battle recorded:
blank `text_unit`, `finish_reason`, `llm_version` and `resolved_at`
on a direction the battle has resolved (`TODO.md` carries the count).
Blank is what the old resolver left
when it could not find the game row by `processed_goal` —
it wrote the battle and skipped the mirror.
The battle holds the only copy of those results,
so they have to move before the directional columns drop
(`docs/game-migration.md`, step 4).
`attempts` rides along, though nothing reports it blank:
the lookup can start failing partway through the retries,
which leaves the game's count behind the battle's final one.

`resolved_at` is what makes a direction safe to touch:
null on the game and set on the battle
means a result that is final and a mirror that never ran.
A direction still in flight is left alone —
its `attempts` is being written as we read,
and resolution mirrors the whole result when it lands.
The id scan offers only unresolved games, and the statement checks again —
not redundant: a direction that resolves between the two is skipped.

Batched, and one statement per direction,
like `backfill_game_input_sha256` and for the same reasons.
Delete this command once a production run leaves nothing to fill,
the way `backfill_game_battles` went once the battle links were in place.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from ...battles import DBGame


FILL_SQL = """
    UPDATE warriors_game g
    SET text_unit_id = b.text_unit_{direction}_id,
        finish_reason = b.finish_reason_{direction},
        llm_version = b.llm_version_{direction},
        attempts = b.attempts_{direction},
        resolved_at = b.resolved_at_{direction}
    FROM warriors_battle b
    WHERE g.id = ANY(%(ids)s)
      AND g.battle_id = b.id
      AND g.warrior_1_id = b.{first}
      AND g.resolved_at IS NULL
      AND b.resolved_at_{direction} IS NOT NULL
"""
DIRECTIONS = (
    ('1_2', 'warrior_1_id'),
    ('2_1', 'warrior_2_id'),
)


class Command(BaseCommand):
    help = 'Fill game rows missing the result their battle has'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=10000)

    def handle(self, *args, batch_size, **options):
        scanned = 0
        filled = 0
        last_id = None
        while True:
            # every unresolved game is a candidate, most of them in flight;
            # the guard sorts them out inside the statement
            games = DBGame.objects.filter(resolved_at=None).order_by('id')
            if last_id is not None:
                games = games.filter(id__gt=last_id)
            ids = list(games.values_list('id', flat=True)[:batch_size])
            if not ids:
                break
            last_id = ids[-1]
            scanned += len(ids)
            with transaction.atomic(), connection.cursor() as cursor:
                for direction, first in DIRECTIONS:
                    cursor.execute(
                        FILL_SQL.format(direction=direction, first=first),
                        {'ids': ids},
                    )
                    filled += cursor.rowcount
            self.stdout.write(f'scanned {scanned}, filled {filled}')
        # unresolved rows are left on purpose, so counting them says nothing
        # about whether this is finished — verify_games answers that
        self.stdout.write(f'done: filled {filled}')
