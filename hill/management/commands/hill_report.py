"""
The counts King of the Hill is judged by ("How it is judged" in docs/king-of-the-hill.md holds the bands).

Read-only, and counts only.
A player is an identity (`hill.identity`), so one person may be several players.
Per round, in players:
- attackers: with an attack that isn't void; counted: with one the round counts (`HillAttemptQuerySet.counted`)
- new: attacking for the first time; returning: the others
- next: attacking again in the next round, once it has closed
- 2nd, cap: with a second attack, and with all of theirs
- shared, via-share: the round's `RoundTally` counts
- ended: how the next round's boss came to the hill
"""
import statistics
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F

from hill.models import (
    AttemptState, BossReason, HillAttempt, Round, RoundTally, TallyKind,
)
from hill.rules import HILL_ATTEMPTS_PER_PLAYER


# The scorecard's windows, in rounds counted from the launch round.
WINDOWS = (('Verdict', range(14, 28)), ('Confirmation', range(28, 42)))
# A post's round and the rounds after it that its traffic swells, left out of the windows and the regulars.
POST_ROUNDS = 3
# A regular attacked in REGULAR_MIN or more of the last REGULAR_SPAN rounds.
REGULAR_MIN = 3
REGULAR_SPAN = 28
# Out of fewer than this, a percentage is noise, so it is left out.
PERCENT_FROM = 50

COLUMNS = ('attackers', 'counted', 'new', 'returning', 'next', '2nd', 'cap', 'shared', 'via-share')


def out_of(part, whole):
    return f'{part} of {whole} ({part / whole:.0%})' if whole >= PERCENT_FROM else f'{part} of {whole}'


def total(rows, name):
    return sum(row[name] for row in rows)


class Command(BaseCommand):
    help = 'Print the counts King of the Hill is judged by: per round, and given --launch, per scorecard window.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--launch', type=int, metavar='N',
            help="The launch post's round: adds its early warnings and the windows.",
        )
        parser.add_argument(
            '--post', type=int, action='append', default=[], metavar='N',
            help=f"A later post's round, left out with the {POST_ROUNDS - 1} after it; repeatable.",
        )
        parser.add_argument(
            '--exclude-identity', action='append', default=[], metavar='IDENTITY',
            help="A player whose attacks the counts leave out, such as the owner; repeatable.",
        )

    def handle(self, *args, launch, post, exclude_identity, **options):
        self.load(exclude_identity)
        if launch is not None and launch not in self.rows:
            raise CommandError(f'There is no Hill #{launch}.')
        # the launch post too: the windows start after its traffic, but the regulars look back across it
        posts = post if launch is None else [launch, *post]
        left_out = {number + after for number in posts for after in range(POST_ROUNDS)}

        self.stdout.write(f"{'hill':<6}{'  '.join(COLUMNS)}  {'ended':<10} outcomes")
        for number, row in self.rows.items():
            columns = '  '.join(f"{'-' if row[name] is None else row[name]:>{len(name)}}" for name in COLUMNS)
            self.stdout.write(f"#{number:<5}{columns}  {row['ended'] or 'open':<10} {row['outcomes']}".rstrip())
        if launch is not None:
            self.early_warnings(launch)
            # ended rounds only: the open one's counts are partial
            in_windows = {number for number, row in self.rows.items() if row['ended'] is not None} - left_out
            for title, offsets in WINDOWS:
                numbers = [launch + offset for offset in offsets if launch + offset in in_windows]
                if numbers:
                    self.window(title, numbers, left_out)
        self.stdout.write(f'\nRegulars now: {self.regulars(max(self.rows, default=0), left_out)}')

    def load(self, excluded):
        self.attacks = defaultdict(Counter)  # live attacks per identity
        sent = defaultdict(list)  # live attack ids, in the order sent
        scored, counted, outcomes = defaultdict(set), defaultdict(set), defaultdict(Counter)
        for attempt in HillAttempt.objects.exclude(identity__in=excluded).annotate(
            number=F('hill_round__number'),
        ).order_by('created_at').values_list('id', 'number', 'identity', 'state', 'late', named=True):
            outcomes[attempt.number][attempt.state] += 1
            outcomes[attempt.number]['late'] += attempt.late
            if attempt.state != AttemptState.VOID:
                self.attacks[attempt.number][attempt.identity] += 1
                sent[attempt.number].append(attempt.id)
            if attempt.state == AttemptState.SCORED:
                scored[attempt.number].add(attempt.identity)
                if not attempt.late:
                    counted[attempt.number].add(attempt.identity)
        tallies = Counter({
            (number, kind): count
            for number, kind, count in RoundTally.objects.values_list('hill_round__number', 'kind', 'count')
        })
        rounds = {
            hill_round.number: hill_round
            for hill_round in Round.objects.annotate(holder=F('boss_attempt__identity')).order_by('number')
        }
        self.first_round = {}
        for number in rounds:
            for identity in self.attacks[number]:
                self.first_round.setdefault(identity, number)

        self.rows = {}
        for number, hill_round in rounds.items():
            attacks = self.attacks[number]
            following = rounds.get(number + 1)
            new = len(self.new_players(number))
            self.rows[number] = {
                'attackers': len(attacks),
                'counted': len(counted[number]),
                'new': new,
                'returning': len(attacks) - new,
                'next': (
                    len(attacks.keys() & self.attacks[number + 1].keys())
                    if following is not None and following.closed_at is not None else None
                ),
                '2nd': sum(count > 1 for count in attacks.values()),
                'cap': sum(count >= HILL_ATTEMPTS_PER_PLAYER for count in attacks.values()),
                'shared': tallies[number, TallyKind.SHARE_PRESSED],
                'via-share': tallies[number, TallyKind.NEW_VIA_SHARE],
                'ended': following.boss_reason if following is not None else None,
                'outcomes': ', '.join(
                    f'{outcome} {outcomes[number][outcome]}'
                    for outcome in (*AttemptState.values, 'late')
                    if outcomes[number][outcome]
                ),
                'scored': len(scored[number]),
                'holder': None if hill_round.holder in excluded else hill_round.holder,
                'broken_early': (
                    following is not None and following.boss_reason == BossReason.BROKE and
                    following.boss_attempt_id in sent[number][:3]
                ),
            }

    def new_players(self, number):
        return {identity for identity in self.attacks[number] if self.first_round[identity] == number}

    def regulars(self, last, left_out):
        rounds_played = Counter(
            identity
            for number in range(last - REGULAR_SPAN + 1, last + 1)
            if number not in left_out
            for identity in self.attacks[number]
        )
        return sum(played >= REGULAR_MIN for played in rounds_played.values())

    def early_warnings(self, launch):
        row = self.rows[launch]
        self.stdout.write(
            f"\nLaunch, Hill #{launch}: {row['attackers']} attackers, "
            f"{out_of(row['2nd'], row['attackers'])} with a 2nd attack",
        )
        if row['next'] is not None:
            new = self.new_players(launch)
            back = len(new & self.attacks[launch + 1].keys())
            self.stdout.write(f'  New players who attacked again in Hill #{launch + 1}: {out_of(back, len(new))}')

    def window(self, title, numbers, left_out):
        rows = [self.rows[number] for number in numbers]
        finished = [row for row in rows if row['next'] is not None]
        player_rounds = total(rows, 'attackers')
        held = Counter(row['holder'] for row in rows if row['holder'] is not None)
        self.stdout.write('\n'.join([
            f'\n{title}, Hill #{numbers[0]} to #{numbers[-1]}, rounds counted: {len(numbers)}',
            f"  1. Attackers per round: median {statistics.median(row['attackers'] for row in rows)}, "
            f'mean {player_rounds / len(rows):.1f}',
            f'  2. Regulars: {self.regulars(numbers[-1], left_out)}; '
            f"next-round return: {out_of(total(finished, 'next'), total(finished, 'attackers'))}",
            f"  3. A 2nd attack: {out_of(total(rows, '2nd'), player_rounds)}; "
            f"at the cap: {out_of(total(rows, 'cap'), player_rounds)}",
            f"  4. Pressed Share: {out_of(total(rows, 'shared'), total(rows, 'scored'))}; "
            f"new through a shared link: {out_of(total(rows, 'via-share'), total(rows, 'new'))}",
            f"  Tuning: beaten {sum(row['ended'] == BossReason.BROKE for row in rows)} times, "
            f"{total(rows, 'broken_early')} by one of the round's first 3 attacks; "
            f"house fallbacks {sum(row['ended'] == BossReason.HOUSE for row in rows)}; "
            f'most rounds held by one player {max(held.values(), default=0)} of {len(rows)}',
        ]))
