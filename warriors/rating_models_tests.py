import datetime

import pytest
from django.utils import timezone

from .models import WarriorArena
from .rating_models import update_rating
from .tests.factories import (
    ArenaFactory, BattleFactory, WarriorArenaFactory, WarriorFactory,
    batch_create_battles,
)


@pytest.mark.django_db
def test_update_rating_takes_newer_battles(battle, warrior_arena, other_warrior_arena, arena):
    then = timezone.now() - datetime.timedelta(days=10)
    # warrior_2 won the first battle
    battle.scheduled_at = then
    battle.resolved_at_1_2 = then
    battle.lcs_len_1_2_1 = 0
    battle.lcs_len_1_2_2 = 6
    battle.resolved_at_2_1 = then
    battle.lcs_len_2_1_1 = 0
    battle.lcs_len_2_1_2 = 6
    battle.save()

    # warrior_1 won the second battle
    new_then = then + datetime.timedelta(days=1)
    BattleFactory(
        arena=battle.arena,
        llm=battle.llm,
        warrior_1=battle.warrior_1,
        warrior_2=battle.warrior_2,
        scheduled_at=new_then,
        resolved_at_1_2=new_then,
        lcs_len_1_2_1=6,
        lcs_len_1_2_2=0,
        resolved_at_2_1=new_then,
        lcs_len_2_1_1=6,
        lcs_len_2_1_2=0,
    )
    warrior_arena_1 = WarriorArena.objects.get(warrior=battle.warrior_1, arena=arena)
    warrior_arena_2 = WarriorArena.objects.get(warrior=battle.warrior_2, arena=arena)

    warrior_arena_1.update_rating()

    warrior_arena_1.refresh_from_db()
    warrior_arena_2.refresh_from_db()
    assert warrior_arena_1.rating > warrior_arena_2.rating


@pytest.mark.django_db
def test_rating_is_isolated_for_each_arena():
    now = timezone.now()
    warrior_1 = WarriorFactory()
    warrior_2 = WarriorFactory()
    if warrior_1.id > warrior_2.id:
        warrior_1, warrior_2 = warrior_2, warrior_1

    arena_1 = ArenaFactory(llm='model1')
    warrior_1_arena_1 = WarriorArenaFactory(warrior=warrior_1, arena=arena_1)
    warrior_2_arena_1 = WarriorArenaFactory(warrior=warrior_2, arena=arena_1)
    BattleFactory(
        arena=arena_1,
        llm=arena_1.llm,
        warrior_1=warrior_1,
        warrior_2=warrior_2,
        resolved_at_1_2=now,
        lcs_len_1_2_1=10,
        lcs_len_1_2_2=1,
        resolved_at_2_1=now,
        lcs_len_2_1_1=10,
        lcs_len_2_1_2=1,
    )

    arena_2 = ArenaFactory(llm='model2')
    warrior_1_arena_2 = WarriorArenaFactory(warrior=warrior_1, arena=arena_2)
    warrior_2_arena_2 = WarriorArenaFactory(warrior=warrior_2, arena=arena_2)
    BattleFactory(
        arena=arena_2,
        llm=arena_2.llm,
        warrior_1=warrior_1,
        warrior_2=warrior_2,
        resolved_at_1_2=now,
        lcs_len_1_2_1=1,
        lcs_len_1_2_2=10,
        resolved_at_2_1=now,
        lcs_len_2_1_1=1,
        lcs_len_2_1_2=10,
    )

    for _ in range(2):
        warrior_1_arena_1.refresh_from_db()
        warrior_1_arena_1.update_rating()
        warrior_2_arena_1.refresh_from_db()
        warrior_2_arena_1.update_rating()
        warrior_1_arena_2.refresh_from_db()
        warrior_1_arena_2.update_rating()
        warrior_2_arena_2.refresh_from_db()
        warrior_2_arena_2.update_rating()

    warrior_1_arena_1.refresh_from_db()
    warrior_2_arena_1.refresh_from_db()
    warrior_1_arena_2.refresh_from_db()
    warrior_2_arena_2.refresh_from_db()

    assert warrior_1_arena_1.rating > 40
    assert warrior_1_arena_1.rating == -warrior_2_arena_1.rating
    assert warrior_2_arena_2.rating == -warrior_1_arena_2.rating
    assert warrior_1_arena_1.rating == warrior_2_arena_2.rating


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'lcs_len_1_2_1': 31,
    'lcs_len_1_2_2': 32,
    'resolved_at_2_1': timezone.now(),
    'lcs_len_2_1_1': 23,
    'lcs_len_2_1_2': 18,
}], indirect=True)
@pytest.mark.parametrize('warrior_arena', [{
    'rating_playstyle': [0, 0],
    'rating_error': 1,
}], indirect=True)
@pytest.mark.parametrize('other_warrior_arena', [{
    'rating_playstyle': [0, 0],
    'rating_error': -1,
}], indirect=True)
def test_update_rating(warrior_arena, other_warrior_arena, battle):
    WarriorArenaFactory.create_batch(3, rating_error=0)  # distraction
    assert warrior_arena.rating == 0.0
    assert other_warrior_arena.rating == 0.0

    update_rating(n=2)

    warrior_arena.refresh_from_db()
    other_warrior_arena.refresh_from_db()
    assert warrior_arena.rating != 0.0
    assert other_warrior_arena.rating != 0.0
    assert warrior_arena.rating_error == pytest.approx(0, abs=0.02)
    assert other_warrior_arena.rating_error == pytest.approx(0.0, abs=0.02)
    assert warrior_arena.rating + other_warrior_arena.rating == pytest.approx(0.0, abs=0.02)


@pytest.mark.django_db
def test_update_rating_creates_missing_warrior_arena(arena, warrior_arena, other_warrior, resolved_battle):
    assert not WarriorArena.objects.filter(warrior=other_warrior, arena=arena).exists()
    warrior_arena.update_rating()
    assert WarriorArena.objects.filter(warrior=other_warrior, arena=arena).exists()


@pytest.mark.django_db
def test_update_rating_does_little_db_hits(arena, warrior_arena, django_assert_max_num_queries):
    n = 100
    batch_create_battles(arena, warrior_arena, n)
    with django_assert_max_num_queries(n // 2):
        warrior_arena.update_rating()
    warrior_arena.refresh_from_db()
    assert warrior_arena.games_played == n
