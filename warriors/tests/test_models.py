from uuid import UUID

import pytest

from ..battles import BattleViewpoint
from ..text_unit import TextUnit
from .factories import BattleFactory, WarriorArenaFactory
from .fixtures import create_scores


@pytest.mark.django_db
def test_battle_score():
    battle = BattleFactory(
        warrior_1__id=UUID(int=1),
        warrior_1__body='asdf',
        warrior_2__id=UUID(int=2),
        warrior_2__body='qwerty',
        text_unit_1_2=TextUnit.get_or_create_by_content('qwerty'),
        lcs_len_1_2_1=0,
        lcs_len_1_2_2=6,
        text_unit_2_1=TextUnit.get_or_create_by_content('qwerty'),
        lcs_len_2_1_1=0,
        lcs_len_2_1_2=6,
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
