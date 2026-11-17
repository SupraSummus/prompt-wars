import datetime

import pytest
from django.utils import timezone

from .battles import LADDER_LLMS, Battle
from .random_matchmaking import (
    create_battle, find_opponents, get_next_battle_delay, schedule_battle,
    schedule_battles,
)
from .tests.factories import BattleFactory, WarriorRatingFactory


@pytest.mark.django_db
def test_schedule_battles_empty():
    schedule_battles()
    assert not Battle.objects.exists()


@pytest.mark.django_db
def test_schedule_battles_no_match(warrior_rating):
    schedule_battles()
    assert not Battle.objects.exists()


@pytest.mark.django_db
def test_schedule_battles():
    warriors = {rating.warrior for rating in WarriorRatingFactory.create_batch(3)}
    schedule_battles()
    participants = set()
    for b in Battle.objects.all():
        participants.add(b.warrior_1)
        participants.add(b.warrior_2)
    assert participants == warriors


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
@pytest.mark.parametrize('other_warrior', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle(warrior, other_warrior, warrior_rating, other_warrior_rating):
    now = datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)

    schedule_battle(now=now)

    battle = Battle.objects.get()
    assert battle.llm in LADDER_LLMS

    # the scheduled warrior's clock advances, and only its: the opponent keeps its turn
    warrior.refresh_from_db()
    other_warrior.refresh_from_db()
    earlier, later = sorted([warrior.next_battle_schedule, other_warrior.next_battle_schedule])
    assert earlier == now
    assert later > now


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle_no_warriors(warrior, warrior_rating):
    now = datetime.datetime(2022, 1, 2, 0, 0, 0, tzinfo=datetime.timezone.utc)
    schedule_battle(now)

    assert not Battle.objects.exists()

    # next_battle_schedule is moved to the future
    warrior.refresh_from_db()
    assert warrior.next_battle_schedule > now


@pytest.mark.django_db
@pytest.mark.parametrize('other_warrior', [{'next_battle_schedule': None}], indirect=True)
def test_a_warrior_off_the_ladder_is_never_paired(warrior, warrior_rating, other_warrior, other_warrior_rating):
    """A King of the Hill attacker has no clock, so matchmaking neither picks it nor pairs it."""
    assert other_warrior not in find_opponents(warrior)
    schedule_battles()
    assert not Battle.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_rating', [{'rating': 0.0}], indirect=True)
@pytest.mark.parametrize(('other_warrior_rating', 'matched'), [
    ({'rating': 2}, False),
    ({'rating': 1.2}, False),
    ({'rating': -1.2}, False),
    ({'rating': 0}, True),
    ({'rating': 1}, True),
    ({'rating': -1}, True),
], indirect=['other_warrior_rating'])
def test_find_opponents_max_rating_diff(warrior, warrior_rating, other_warrior, other_warrior_rating, matched):
    opponents = find_opponents(warrior, max_rating_diff=1.2)
    assert (other_warrior in opponents) is matched


@pytest.mark.django_db
@pytest.mark.parametrize('other_warrior', [
    {'moderation_passed': False},
    {'moderation_passed': None},
], indirect=True)
def test_find_opponents_exclude_not_worthy(warrior, warrior_rating, other_warrior, other_warrior_rating):
    opponents = find_opponents(warrior)
    assert other_warrior not in opponents


@pytest.mark.django_db
@pytest.mark.parametrize('battle_exists', [True, False])
def test_find_opponents_exclude_already_battled(warrior, other_warrior, other_warrior_rating, battle_exists):
    if battle_exists:
        Battle.create_from_warriors(warrior, other_warrior)
    opponents = find_opponents(warrior)
    opponent_expected = not battle_exists
    assert (other_warrior in opponents) is opponent_expected


@pytest.mark.django_db
def test_create_battle_lots_of_battles(warrior, other_warrior, battle):
    BattleFactory.create_batch(
        100,
        warrior_1=battle.warrior_1,
        warrior_2=battle.warrior_2,
    )
    opponent_clock = other_warrior.next_battle_schedule

    create_battle(warrior, other_warrior)

    # 102 battles: 1 from the fixture, 100 created in this test, 1 created in create_battle
    warrior.refresh_from_db()
    assert warrior.next_battle_schedule > timezone.now() + datetime.timedelta(days=365 * 10)
    # being picked does not spend the opponent's turn
    other_warrior.refresh_from_db()
    assert other_warrior.next_battle_schedule == opponent_clock


@pytest.mark.parametrize(
    ('battle_count', 'min_delay_minutes', 'max_delay_minutes'),
    [
        (0, 0, 0),
        (1, 0, 1),
        (2, 1, 3),
        (3, 3, 7),
        (4, 7, 15),
    ],
)
def test_next_battle_delay(battle_count, min_delay_minutes, max_delay_minutes):
    delay = get_next_battle_delay(battle_count)
    assert delay >= datetime.timedelta(minutes=min_delay_minutes)
    assert delay <= datetime.timedelta(minutes=max_delay_minutes)
