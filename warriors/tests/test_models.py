import datetime
from uuid import UUID

import pytest

from ..models import RATING_TRANSFER_COEFFICIENT
from .factories import BattleFactory, WarriorFactory


@pytest.mark.django_db
def test_find_opponent_self(warrior):
    opponent = warrior.find_opponent(exclude_warriors=())
    assert opponent == warrior


@pytest.mark.django_db
def test_find_opponent_exclude(warrior):
    opponent = warrior.find_opponent(exclude_warriors=[warrior.id])
    assert opponent is None


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'rating': 0.0}], indirect=True)
@pytest.mark.parametrize(
    ('other_rating', 'matched'),
    [
        (2, False),
        (1.2, False),
        (-1.2, False),
        (0, True),
        (1, True),
        (-1, True),
    ],
)
def test_find_opponents_max_rating_diff(warrior, other_rating, matched):
    other = WarriorFactory(rating=other_rating)
    opponents = warrior.find_opponents(max_rating_diff=1.2)
    assert (other in opponents) is matched


@pytest.mark.django_db
@pytest.mark.parametrize('moderation_passed', [False, None])
def test_find_opponents_exclude_not_worthy(warrior, moderation_passed):
    other = WarriorFactory(moderation_passed=moderation_passed)
    opponents = warrior.find_opponents()
    assert other not in opponents


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle_clears_next_battle_schedule(warrior):
    other = WarriorFactory(next_battle_schedule=warrior.next_battle_schedule)
    assert warrior.next_battle_schedule is not None
    assert other.next_battle_schedule is not None

    battle = warrior.schedule_battle(now=warrior.next_battle_schedule)
    assert battle is not None

    warrior.refresh_from_db()
    other.refresh_from_db()
    assert warrior.next_battle_schedule is None
    assert other.next_battle_schedule is None


@pytest.mark.django_db
def test_battle_rating_gained():
    battle = BattleFactory(
        warrior_1__id=UUID(int=1),
        warrior_1__body='asdf',
        warrior_2__id=UUID(int=2),
        warrior_2__body='qwerty',
        result_1_2='qwerty',
        result_2_1='qwerty',
        warrior_1_rating=0.0,
        warrior_2_rating=0.0,
    )

    # lets consider a single game there - the one where propmt is warrior_1 || warrior_2
    game = battle.view_1
    assert game.score == 0  # this means that warrior_1 was totaly erased, and warrior_2 totally preserved
    # warrior_1 lost as many points as possible to an equaly skilled opponent
    assert game.rating_gained == -RATING_TRANSFER_COEFFICIENT * 0.5

    # second game - warrior_2 || warrior_1
    assert battle.view_2.score == 1
    assert battle.view_2.rating_gained == RATING_TRANSFER_COEFFICIENT * 0.5

    # overall we have maximum rating gain
    assert battle.rating_gained == -RATING_TRANSFER_COEFFICIENT * 0.5
