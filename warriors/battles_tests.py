from uuid import UUID

import pytest

from .battles import Battle, BattleViewpoint
from .tests.factories import BattleFactory, WarriorArenaFactory
from .tests.fixtures import create_scores
from .text_unit import TextUnit


@pytest.mark.django_db
def test_battle_score():
    battle = BattleFactory(
        warrior_1__id=UUID(int=1),
        warrior_1__body='asdf',
        warrior_2__id=UUID(int=2),
        warrior_2__body='qwerty',
        text_unit_1_2=TextUnit.get_or_create_by_content('qwerty'),
        text_unit_2_1=TextUnit.get_or_create_by_content('qwerty'),
    )
    create_scores(battle, 0, 1, 0, 1)
    battle_viewpoint = BattleViewpoint(battle, '1')

    # lets consider a single game there - the one where propmt is warrior_1 || warrior_2
    game = battle_viewpoint.game_1_2
    assert game.score == 0  # this means that warrior_1 was totaly erased, and warrior_2 totally preserved

    # second game - warrior_2 || warrior_1
    assert battle_viewpoint.game_2_1.score == 1

    assert battle_viewpoint.score == 0

    # to compute performance we must assign warrior_arens (not in the db)
    battle.warrior_arena_1 = WarriorArenaFactory(warrior=battle.warrior_1, rating_playstyle=[0, 0])
    battle.warrior_arena_2 = WarriorArenaFactory(warrior=battle.warrior_2, rating_playstyle=[0, 0])
    assert battle_viewpoint.performance == pytest.approx(-0.5, abs=0.01)  # it could have been closer to 1 if there was a discrepancy in the ratings


# transaction=True runs the test in autocommit, like a plain view request;
# under the default test-wrapping transaction the timestamps would agree
# even without create_from_warriors' own atomic block.
@pytest.mark.django_db(transaction=True)
def test_create_from_warriors_scheduled_at_consistent(warrior_arena, other_warrior_arena):
    battle, db_game_1_2, db_game_2_1 = Battle.create_from_warriors(warrior_arena, other_warrior_arena)
    battle.refresh_from_db()
    db_game_1_2.refresh_from_db()
    db_game_2_1.refresh_from_db()
    assert db_game_1_2.scheduled_at == battle.scheduled_at
    assert db_game_2_1.scheduled_at == battle.scheduled_at
