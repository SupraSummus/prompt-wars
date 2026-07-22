import pytest
from django.core.management import call_command

from ..battles import DBGame
from .factories import BattleFactory, WarriorFactory


@pytest.mark.django_db
def test_backfill_links_both_directions():
    warrior_a = WarriorFactory()
    warrior_b = WarriorFactory()
    warrior_1, warrior_2 = sorted([warrior_a, warrior_b], key=lambda w: w.id)
    battle = BattleFactory(llm='openai-gpt', warrior_1=warrior_1, warrior_2=warrior_2)
    game_1_2 = DBGame.objects.create(
        battle=None,
        llm=battle.llm,
        warrior_1=warrior_1,
        warrior_2=warrior_2,
        scheduled_at=battle.scheduled_at,
    )
    game_2_1 = DBGame.objects.create(
        battle=None,
        llm=battle.llm,
        warrior_1=warrior_2,
        warrior_2=warrior_1,
        scheduled_at=battle.scheduled_at,
    )

    call_command('backfill_game_battles', batch_size=1)

    game_1_2.refresh_from_db()
    game_2_1.refresh_from_db()
    assert game_1_2.battle_id == battle.id
    assert game_2_1.battle_id == battle.id


@pytest.mark.django_db
def test_backfill_leaves_unmatched_rows_null():
    warrior_a = WarriorFactory()
    warrior_b = WarriorFactory()
    game = DBGame.objects.create(
        battle=None,
        llm='openai-gpt',
        warrior_1=warrior_a,
        warrior_2=warrior_b,
    )

    call_command('backfill_game_battles')

    game.refresh_from_db()
    assert game.battle_id is None
