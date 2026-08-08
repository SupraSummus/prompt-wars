from uuid import UUID

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from .battles import Battle, BattleViewpoint
from .tests.factories import BattleFactory, WarriorArenaFactory, WarriorFactory
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


@pytest.fixture
def scored_battle():
    battle = BattleFactory(
        warrior_1__id=UUID(int=1),
        warrior_2__id=UUID(int=2),
    )
    create_scores(
        battle,
        score_1_2_1=0.1, score_1_2_2=0.2,
        score_2_1_1=0.3, score_2_1_2=0.4,
    )
    return battle


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('viewpoint', 'game_name', 'similarities'),
    (
        ('1', 'game_1_2', (0.1, 0.2)),
        ('1', 'game_2_1', (0.4, 0.3)),
        ('2', 'game_1_2', (0.4, 0.3)),
        ('2', 'game_2_1', (0.1, 0.2)),
    ),
)
def test_game_reports_its_own_similarities(scored_battle, viewpoint, game_name, similarities):
    """
    A game reports the similarities of its own LLM run,
    warrior 1 being the one its prompt concatenated first.
    Both viewpoints see the same two games, in opposite slots.
    """
    game = getattr(BattleViewpoint(scored_battle, viewpoint), game_name)
    assert (
        game.warrior_1_preserved_ratio,
        game.warrior_2_preserved_ratio,
    ) == similarities


@pytest.mark.django_db
def test_battle_score_splits_between_viewpoints(scored_battle):
    """
    The two viewpoints of a battle split one outcome between them.
    Selecting a game and labelling its warriors are separate steps,
    and getting one right while the other is wrong
    leaves the pair summing to something other than 1.
    """
    assert (
        BattleViewpoint(scored_battle, '1').score +
        BattleViewpoint(scored_battle, '2').score
    ) == pytest.approx(1)


@pytest.mark.django_db
def test_reading_scores_costs_no_query_per_battle():
    """
    A game reaches its score through the game row the score names,
    so a read path fetching battles without their games
    pays one query per score row.
    The scores come out right either way,
    which leaves the query count as the only thing that shows it.
    """
    warrior = WarriorFactory(id=UUID(int=1))

    def add_battle(warrior_2_id):
        battle = BattleFactory(warrior_1=warrior, warrior_2__id=UUID(int=warrior_2_id))
        create_scores(
            battle,
            score_1_2_1=0.1, score_1_2_2=0.2,
            score_2_1_1=0.3, score_2_1_2=0.4,
        )

    def queries_to_score_every_battle():
        with CaptureQueriesContext(connection) as queries:
            for battle in Battle.objects.prefetch_related('game_scores__game'):
                BattleViewpoint(battle, '1').score
        return len(queries)

    add_battle(2)
    one_battle = queries_to_score_every_battle()
    for warrior_2_id in range(3, 6):
        add_battle(warrior_2_id)
    assert queries_to_score_every_battle() == one_battle


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
