import pytest

from .matchmaking_challenge import get_strongest_opponents
from .tests.factories import WarriorArenaFactory


@pytest.mark.django_db
@pytest.mark.parametrize('playstyle', [
    [0.0, 0.0],
    [1.0, 1.0],
])
def test_get_strongest_opponents_no_playstyle_diff(arena, playstyle):
    warrior = WarriorArenaFactory(
        arena=arena,
        rating_playstyle=playstyle,
    )
    strong_opponent = WarriorArenaFactory(
        arena=arena,
        rating_playstyle=playstyle,
        rating=12,
    )
    weak_opponent = WarriorArenaFactory(
        arena=arena,
        rating_playstyle=playstyle,
        rating=10,
    )
    opponents = list(get_strongest_opponents(warrior))
    assert opponents == [strong_opponent, weak_opponent]


@pytest.mark.django_db
@pytest.mark.parametrize('rating', [
    0,
    7,
])
def test_get_strongest_opponents_no_rating_diff(arena, rating):
    warrior = WarriorArenaFactory(
        arena=arena,
        rating_playstyle=[1, 1],
    )
    strong_opponent = WarriorArenaFactory(
        arena=arena,
        rating=rating,
        rating_playstyle=[1, 0],
    )
    weak_opponent = WarriorArenaFactory(
        arena=arena,
        rating=rating,
        rating_playstyle=[0, 1],
    )
    opponents = list(get_strongest_opponents(warrior))
    assert opponents == [strong_opponent, weak_opponent]


@pytest.mark.django_db
def test_get_strongest_opponents(arena):
    warrior = WarriorArenaFactory(
        arena=arena,
        rating_playstyle=[10, 9],
    )
    strong_opponent = WarriorArenaFactory(
        arena=arena,
        rating=80,
        rating_playstyle=[2, -1],
    )
    weak_opponent = WarriorArenaFactory(
        arena=arena,
        rating=120,
        rating_playstyle=[1, 4],
    )
    opponents = list(get_strongest_opponents(warrior))
    assert opponents == [strong_opponent, weak_opponent]
    assert opponents[0].relative_rating == (80 - (-9 * 2 + 10 * -1))
    assert opponents[1].relative_rating == (120 - (-9 * 1 + 10 * 4))
