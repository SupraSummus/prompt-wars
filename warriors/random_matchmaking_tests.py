import datetime

import pytest
from django.utils import timezone

from .battles import Battle
from .models import WarriorArena
from .random_matchmaking import (
    create_battle, find_opponents, get_next_battle_delay, schedule_battle,
    schedule_battles,
)
from .tests.factories import BattleFactory, WarriorArenaFactory


@pytest.mark.django_db
def test_schedule_battles_empty():
    assert not WarriorArena.objects.exists()
    schedule_battles()


@pytest.mark.django_db
def test_schedule_battles_no_match(warrior_arena):
    schedule_battles()
    assert not Battle.objects.exists()


@pytest.mark.django_db
def test_schedule_battles(arena):
    warriors = set(WarriorArenaFactory.create_batch(
        3,
        arena=arena,
        next_battle_schedule=timezone.now(),
    ))
    schedule_battles()
    participants = set()
    for b in Battle.objects.all():
        participants.add(b.warrior_1)
        participants.add(b.warrior_2)
    assert participants == {w.warrior for w in warriors}


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
@pytest.mark.parametrize('other_warrior_arena', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle(arena, warrior_arena, other_warrior_arena):
    now = datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    assert warrior_arena.next_battle_schedule is not None
    assert other_warrior_arena.next_battle_schedule is not None

    schedule_battle(now=now)

    battle = Battle.objects.get()
    assert battle.arena == arena
    assert battle.llm
    assert battle.llm == arena.llm

    warrior_arena.refresh_from_db()
    # it advances the next_battle_schedule
    assert warrior_arena.next_battle_schedule > now


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle_no_warriors(warrior_arena):
    now = datetime.datetime(2022, 1, 2, 0, 0, 0, tzinfo=datetime.timezone.utc)
    schedule_battle(now)

    assert not Battle.objects.exists()

    # next_battle_schedule is moved to the future
    warrior_arena.refresh_from_db()
    assert warrior_arena.next_battle_schedule > now


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{'rating': 0.0}], indirect=True)
@pytest.mark.parametrize(('other_warrior_arena', 'matched'), [
    ({'rating': 2}, False),
    ({'rating': 1.2}, False),
    ({'rating': -1.2}, False),
    ({'rating': 0}, True),
    ({'rating': 1}, True),
    ({'rating': -1}, True),
], indirect=['other_warrior_arena'])
def test_find_opponents_max_rating_diff(warrior_arena, other_warrior_arena, matched):
    opponents = find_opponents(warrior_arena, max_rating_diff=1.2)
    assert (other_warrior_arena in opponents) is matched


@pytest.mark.django_db
@pytest.mark.parametrize('other_warrior', [
    {'moderation_passed': False},
    {'moderation_passed': None},
], indirect=True)
def test_find_opponents_exclude_not_worthy(warrior_arena, other_warrior_arena):
    opponents = find_opponents(warrior_arena)
    assert other_warrior_arena not in opponents


@pytest.mark.django_db
@pytest.mark.parametrize('battle_exists', [True, False])
def test_find_opponents_exclude_already_battled(warrior_arena, other_warrior_arena, battle_exists):
    if battle_exists:
        battle, _, _ = Battle.create_from_warriors(warrior_arena, other_warrior_arena)
    opponents = find_opponents(warrior_arena)
    opponent_expected = not battle_exists
    assert (other_warrior_arena in opponents) is opponent_expected


@pytest.mark.django_db
def test_create_battle_lots_of_games_played(warrior_arena, battle, other_warrior_arena):
    BattleFactory.create_batch(
        100,
        arena=battle.arena,
        llm=battle.llm,
        warrior_1=battle.warrior_1,
        warrior_2=battle.warrior_2,
    )
    create_battle(warrior_arena, other_warrior_arena)
    warrior_arena.refresh_from_db()
    assert warrior_arena.games_played == 102  # 1 from fixture, 100 created in this test, 1 created in create_battle
    assert warrior_arena.next_battle_schedule > timezone.now() + datetime.timedelta(days=365 * 10)

    # opponent has games_played recalculated
    other_warrior_arena.refresh_from_db()
    assert other_warrior_arena.games_played == 102


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('warrior_arena', 'min_delay_minutes', 'max_delay_minutes'),
    [
        ({'games_played': 0}, 0, 0),
        ({'games_played': 1}, 0, 1),
        ({'games_played': 2}, 1, 3),
        ({'games_played': 3}, 3, 7),
        ({'games_played': 4}, 7, 15),
    ],
    indirect=['warrior_arena'],
)
def test_next_battle_delay(warrior_arena, min_delay_minutes, max_delay_minutes):
    delay = get_next_battle_delay(warrior_arena)
    assert delay >= datetime.timedelta(minutes=min_delay_minutes)
    assert delay <= datetime.timedelta(minutes=max_delay_minutes)
