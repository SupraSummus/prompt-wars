import datetime
from uuid import UUID

import pytest

from ..models import Battle
from .factories import BattleFactory


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'rating': 0.0}], indirect=True)
@pytest.mark.parametrize(('other_warrior', 'matched'), [
    ({'rating': 2}, False),
    ({'rating': 1.2}, False),
    ({'rating': -1.2}, False),
    ({'rating': 0}, True),
    ({'rating': 1}, True),
    ({'rating': -1}, True),
], indirect=['other_warrior'])
def test_find_opponents_max_rating_diff(warrior, other_warrior, matched):
    opponents = warrior.find_opponents(max_rating_diff=1.2)
    assert (other_warrior in opponents) is matched


@pytest.mark.django_db
@pytest.mark.parametrize('other_warrior', [
    {'moderation_passed': False},
    {'moderation_passed': None},
], indirect=True)
def test_find_opponents_exclude_not_worthy(warrior, other_warrior):
    opponents = warrior.find_opponents()
    assert other_warrior not in opponents


@pytest.mark.django_db
@pytest.mark.parametrize('battle_exists', [True, False])
def test_find_opponents_exclude_already_battled(warrior, other_warrior, battle_exists):
    if battle_exists:
        Battle.create_from_warriors(warrior, other_warrior)
    opponents = warrior.find_opponents()
    opponent_expected = not battle_exists
    assert (other_warrior in opponents) is opponent_expected


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
@pytest.mark.parametrize('other_warrior', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle(arena, warrior, other_warrior):
    assert warrior.next_battle_schedule is not None
    assert other_warrior.next_battle_schedule is not None

    battle = warrior.schedule_battle(now=warrior.next_battle_schedule)
    assert battle is not None
    assert battle.arena == arena

    warrior.refresh_from_db()
    other_warrior.refresh_from_db()
    # it clears the next_battle_schedule
    assert warrior.next_battle_schedule is None
    assert other_warrior.next_battle_schedule is None


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
    'games_played': 2,
}], indirect=True)
def test_schedule_battle_no_warriors(warrior):
    now = datetime.datetime(2022, 1, 2, 0, 0, 0, tzinfo=datetime.timezone.utc)
    battle = warrior.schedule_battle(now)
    assert battle is None

    # next_battle_schedule is moved to the future
    warrior.refresh_from_db()
    assert warrior.next_battle_schedule > now


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('warrior', 'min_delay_minutes', 'max_delay_minutes'),
    [
        ({'games_played': 0}, 0, 0),
        ({'games_played': 1}, 0, 1),
        ({'games_played': 2}, 1, 3),
        ({'games_played': 3}, 3, 7),
        ({'games_played': 4}, 7, 15),
    ],
    indirect=['warrior'],
)
def test_next_battle_delay(warrior, min_delay_minutes, max_delay_minutes):
    delay = warrior.get_next_battle_delay()
    assert delay >= datetime.timedelta(minutes=min_delay_minutes)
    assert delay <= datetime.timedelta(minutes=max_delay_minutes)


@pytest.mark.django_db
def test_battle_score():
    battle = BattleFactory(
        warrior_1__id=UUID(int=1),
        warrior_1__body='asdf',
        warrior_1__rating_playstyle=[0, 0],
        warrior_2__id=UUID(int=2),
        warrior_2__body='qwerty',
        warrior_2__rating_playstyle=[0, 0],
        result_1_2='qwerty',
        lcs_len_1_2_1=0,
        lcs_len_1_2_2=6,
        result_2_1='qwerty',
        lcs_len_2_1_1=0,
        lcs_len_2_1_2=6,
    )

    # lets consider a single game there - the one where propmt is warrior_1 || warrior_2
    game = battle.game_1_2
    assert game.score == 0  # this means that warrior_1 was totaly erased, and warrior_2 totally preserved

    # second game - warrior_2 || warrior_1
    assert battle.game_2_1.score == 1

    assert battle.score == 0
    assert battle.performance == -0.5  # it could have been closer to -1 if there was a discrepancy in the ratings
