import datetime

import pytest
from django.utils import timezone

from .rating_models import update_rating
from .tests.factories import BattleFactory, WarriorArenaFactory


@pytest.mark.django_db
def test_update_rating_takes_newer_battles(battle):
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

    battle.warrior_1.update_rating()

    battle.warrior_1.refresh_from_db()
    battle.warrior_2.refresh_from_db()
    assert battle.warrior_1.rating > battle.warrior_2.rating


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
