from uuid import UUID

import pytest

from .battles import BattleViewpoint
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
        text_unit_2_1=TextUnit.get_or_create_by_content('asdf qwerty'),
    )
    create_scores(
        battle,
        score_1_2_1=0, score_1_2_2=1,  # asdf || qwerty
        score_2_1_1=0.3, score_2_1_2=0.6,  # qwerty || asdf
    )

    # to compute performance we must assign warrior_arens (not in the db)
    battle.warrior_arena_1 = WarriorArenaFactory(warrior=battle.warrior_1, rating_playstyle=[0, 0])
    battle.warrior_arena_2 = WarriorArenaFactory(warrior=battle.warrior_2, rating_playstyle=[0, 0])

    battle_viewpoint = BattleViewpoint(battle, '1')
    assert battle_viewpoint.performance == pytest.approx(-1 / 3)  # it could have been closer to 1 if there was a discrepancy in the ratings


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('viewpoint', 'game', 'expected_similarities'),
    (
        ('1', 'game_1_2', (0.1, 0.2)),
        ('1', 'game_2_1', (0.4, 0.3)),
        ('2', 'game_1_2', (0.3, 0.4)),  # from the second warror viewpoint first game is 2 || 1
        ('2', 'game_2_1', (0.2, 0.1)),
    ),
)
def test_game_score_object(viewpoint, game, expected_similarities):
    battle = BattleFactory(
        warrior_1__id=UUID(int=1),
        warrior_2__id=UUID(int=2),
    )
    create_scores(
        battle,
        score_1_2_1=0.1, score_1_2_2=0.2,
        score_2_1_1=0.3, score_2_1_2=0.4,
    )
    viewpoint = BattleViewpoint(battle, viewpoint)
    game = getattr(viewpoint, game)
    assert (
        game.score_object.warrior_1_similarity,
        game.score_object.warrior_2_similarity,
    ) == expected_similarities
