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
def test_find_opponents_range(warrior):
    below = [
        WarriorFactory(rating=-(n + 1))
        for n in range(3)
    ]
    above = [
        WarriorFactory(rating=n + 1)
        for n in range(3)
    ]
    equal = WarriorFactory(rating=0)
    opponents = warrior.find_opponents(
        rating_range=2,
        exclude_warriors=[warrior.id],
    )
    assert {*opponents} == {
        below[0], below[1],
        above[0], above[1],
        equal,
    }
