import pytest

from .models import Warrior
from .stats import ArenaStats, create_arena_stats
from .tests.factories import WarriorFactory


@pytest.mark.django_db
def test_create_arena_stats_empty(arena):
    create_arena_stats()
    stats = ArenaStats.objects.get()
    assert stats.arena == arena
    assert stats.warrior_count == 0
    assert stats.battle_count == 0


@pytest.mark.django_db
def test_create_arena_stats(arena):
    warriors = [
        WarriorFactory.build(arena=arena, rating=rating, moderation_passed=True)
        for rating in range(10)
    ]
    Warrior.objects.bulk_create(warriors)
    create_arena_stats()
    stats = ArenaStats.objects.get()
    assert stats.arena == arena
    assert stats.warrior_count == 10
    assert stats.battle_count == 0
    assert len(stats.rating_quantiles) == 101
    assert stats.rating_quantiles[0] == 0
    assert stats.rating_quantiles[100] == 9
