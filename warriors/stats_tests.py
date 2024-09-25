import pytest

from .stats import ArenaStats, create_arena_stats
from .tests.factories import WarriorArenaFactory


@pytest.mark.django_db
def test_create_arena_stats_empty(arena):
    create_arena_stats()
    stats = ArenaStats.objects.get()
    assert stats.arena == arena
    assert stats.warrior_count == 0
    assert stats.battle_count == 0


@pytest.mark.django_db
def test_create_arena_stats(arena):
    for rating in range(10):
        WarriorArenaFactory.create(
            arena=arena, rating=rating,
            warrior__moderation_passed=True,
        )
    create_arena_stats()
    stats = ArenaStats.objects.get()
    assert stats.arena == arena
    assert stats.warrior_count == 10
    assert stats.battle_count == 0
    assert len(stats.rating_quantiles) == 101
    assert stats.rating_quantiles[0] == 0
    assert stats.rating_quantiles[100] == 9
