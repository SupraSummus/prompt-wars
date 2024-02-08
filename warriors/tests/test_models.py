import datetime

import pytest

from .factories import WarriorFactory


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
