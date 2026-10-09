import io

import pytest
from django.core.management import call_command
from django.utils import timezone

from ..models import AttemptState, Round, RoundTally, TallyKind
from .factories import HillAttemptFactory, RoundFactory


def report(*args):
    out = io.StringIO()
    call_command('hill_report', *map(str, args), stdout=out)
    return out.getvalue()


def rounds(count):
    """Rounds 1 to `count`, the last one open."""
    for number in range(1, count + 1):
        RoundFactory(number=number, closed_at=timezone.now() if number < count else None)


def attack(number, *identities, **kwargs):
    hill_round = Round.objects.get(number=number)
    for identity in identities:
        HillAttemptFactory(hill_round=hill_round, identity=identity, **kwargs)


@pytest.mark.django_db
def test_each_round_counts_its_players_and_share_presses():
    rounds(3)
    attack(1, 'ann', 'ann', 'bob', 'owner')
    attack(1, 'bob', state=AttemptState.VOID)
    attack(2, 'ann', 'cat')
    attack(3, 'bob')
    RoundTally.bump(Round.objects.get(number=2).id, TallyKind.SHARE_PRESSED)

    lines = report('--exclude-identity', 'owner').splitlines()

    header = lines[0].split()
    table = [dict(zip(header, line.split())) for line in lines[1:4]]
    columns = ('attackers', 'new', 'returning', 'next', '2nd', 'shared', 'via-share')
    assert [tuple(row[name] for name in columns) for row in table] == [
        ('2', '2', '0', '1', '1', '0', '0'),
        # the third round is open, so who comes back from the second isn't known yet
        ('2', '1', '1', '-', '0', '1', '0'),
        ('1', '0', '1', '-', '0', '0', '0'),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize('posts, verdict, regulars, came_back', [
    ((), '#15 to #17', 2, '2 of 3'),
    # the post's round and the 2 after it
    ((16,), '#15 to #15', 1, '1 of 2'),
])
def test_posts_are_left_out_of_the_windows_and_the_regulars(posts, verdict, regulars, came_back):
    rounds(18)
    for number in (1, 2, 3):
        attack(number, 'brought by the launch')
    for number in (5, 9, 15):
        attack(number, 'regular')
    for number in (15, 16, 17):
        attack(number, 'brought by the post')

    output = report('--launch', 1, *(f'--post={number}' for number in posts))

    # the open round's counts are partial, so no window takes it
    assert f'Verdict, Hill {verdict},' in output
    # below the size a percentage needs, just the counts
    assert f'2. Regulars: {regulars}; next-round return: {came_back}\n' in output
    assert output.endswith(f'Regulars now: {regulars}\n')
