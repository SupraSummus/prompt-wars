"""
Audit every battle direction against its game row.
Read-only: it reports, and repairing is a separate deliberate act —
one command per named cause, alongside this one.

This checks the invariant every step of docs/game-migration.md rests on:
a battle direction always has its game row,
and the two agree for as long as both copies exist.
`resolve_battle` writes the game row
and mirrors it onto the battle's directional columns;
the audit compares them without caring which side is authoritative,
because equality is symmetric.

Nothing here is routine backfill.
`Battle.create_from_warriors` writes a battle and both its games
in one transaction, so a missing row is a broken invariant, not a gap;
a blank game field means only the battle column ever got the value;
a disagreement means the two were written differently.
Each is a bug to explain rather than data to copy over —
and the directional columns cannot be dropped while any remain.

Findings are counted per category with one example row, never listed:
one bad backfill leaves a finding on every battle in the table,
and a page of identical lines is where the single odd one hides.

Batched by battle id to bound memory, not for locking:
the audit takes no locks and can be interrupted at any point.
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from ...battles import Battle, as_bytes, mirrored_game_fields


class Command(BaseCommand):
    help = 'Report game rows that do not mirror their battle'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=1000)

    def handle(self, *args, batch_size, **options):
        self.scanned = 0
        self.unresolved = 0
        self.findings = Counter()
        self.examples = {}
        last_id = None
        while True:
            battles = Battle.objects.order_by('id')
            if last_id is not None:
                battles = battles.filter(id__gt=last_id)
            battles = list(battles.prefetch_related('games')[:batch_size])
            if not battles:
                break
            last_id = battles[-1].id
            self.scanned += len(battles)
            for battle in battles:
                self.check_battle(battle)
            self.stdout.write(self.counts())
        if self.findings:
            raise CommandError(self.report())
        self.stdout.write(self.report())

    def check_battle(self, battle):
        games = {game.warrior_1_id: game for game in battle.games.all()}
        for direction in ('1_2', '2_1'):
            fields = mirrored_game_fields(battle, direction)
            game = games.pop(fields['warrior_1_id'], None)
            location = f'battle {battle.id} game {direction}'
            if game is None:
                self.record('missing game row', location)
            elif game.resolved_at is None:
                # A direction still in flight is being written as we read:
                # attempts climbs on every retry, and the battle and its
                # games arrive in separate queries, so comparing them
                # invites a finding that is not one. The gate is the game
                # row's own resolved_at — keyed on the mirrored column, a
                # resolution the mirror never reached would read as in
                # flight and never get compared.
                self.unresolved += 1
            else:
                self.check_game(game, fields, location)
        for warrior_1_id in games:
            self.record(
                'game row outside the battle pair',
                f'battle {battle.id} warrior {warrior_1_id}',
            )

    def check_game(self, game, fields, location):
        for name, expected in fields.items():
            actual = as_bytes(getattr(game, name))
            if actual == expected:
                continue
            kind = 'blank' if not actual else 'conflicting'
            self.record(f'{kind} {name}', location)

    def record(self, category, location):
        self.findings[category] += 1
        # one example is a place to start looking; three would read as a
        # sample, and the first three by battle id are not one
        self.examples.setdefault(category, location)

    def counts(self):
        return (
            f'scanned {self.scanned}, left {self.unresolved} in flight, '
            f'{sum(self.findings.values())} findings'
        )

    def report(self):
        return '\n'.join([self.counts()] + [
            f'{category}: {count} (e.g. {self.examples[category]})'
            for category, count in self.findings.most_common()
        ])
