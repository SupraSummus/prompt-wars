"""
Check that every battle direction has a game row mirroring it,
and create the rows that are missing.

This backs the invariant every step of docs/game-migration.md rests on:
a battle direction always has its game row,
faithful to the battle's directional columns
for as long as the battle is the authoritative writer.
New battles get both rows inside the battle's own transaction
(`Battle.create_from_warriors`), so what this walks is the older rows.

Batched by battle id, each batch its own transaction:
it holds no long locks and can be interrupted and rerun.

A mismatch is reported, never overwritten.
While the battle is still the authoritative writer,
a drifted row means something wrote the pair inconsistently —
a bug to look at, not data to paper over —
so the command exits nonzero and leaves the row alone.

Created rows get no `processed_goal`:
a legacy battle's resolution goal cannot be recovered
(the field is `SET_NULL` and goals are garbage collected),
which is why the game lookup in `resolve_battle`
moves to the unique (battle, warrior_1) — every row has that.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...battles import Battle, DBGame, as_bytes, mirrored_game_fields


class Command(BaseCommand):
    help = 'Verify game rows mirror their battle, creating missing ones'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=1000)

    def handle(self, *args, batch_size, **options):
        self.created = 0
        self.mismatches = 0
        self.unexpected = 0
        scanned = 0
        last_id = None
        while True:
            battles = Battle.objects.order_by('id')
            if last_id is not None:
                battles = battles.filter(id__gt=last_id)
            battles = list(battles.prefetch_related('games')[:batch_size])
            if not battles:
                break
            last_id = battles[-1].id
            scanned += len(battles)
            with transaction.atomic():
                for battle in battles:
                    self.check_battle(battle)
            self.stdout.write(f'scanned {scanned}, {self.tally()}')
        if self.mismatches or self.unexpected:
            raise CommandError(self.tally())

    def tally(self):
        return (
            f'created {self.created}, '
            f'{self.mismatches} mismatched fields, '
            f'{self.unexpected} unexpected rows'
        )

    def check_battle(self, battle):
        games = {game.warrior_1_id: game for game in battle.games.all()}
        for direction in ('1_2', '2_1'):
            fields = mirrored_game_fields(battle, direction)
            game = games.pop(fields['warrior_1_id'], None)
            if game is None:
                DBGame.objects.create(battle=battle, **fields)
                self.created += 1
                continue
            for name, expected in fields.items():
                actual = as_bytes(getattr(game, name))
                if actual != expected:
                    self.stdout.write(
                        f'battle {battle.id} game {direction}: '
                        f'{name} is {actual!r}, battle says {expected!r}'
                    )
                    self.mismatches += 1
        for warrior_1_id in games:
            self.stdout.write(
                f'battle {battle.id}: game row of warrior {warrior_1_id} '
                f'is not a direction of this battle'
            )
            self.unexpected += 1
