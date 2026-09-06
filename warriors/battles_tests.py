from uuid import UUID

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .battles import Battle
from .score import ScoreAlgorithm
from .tests.factories import (
    BattleFactory, GameScoreFactory, WarriorArenaFactory, WarriorFactory,
    game_of,
)
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
    game_1_2, game_2_1 = battle.games_list

    # lets consider a single game there - the one where propmt is warrior_1 || warrior_2
    score = battle.score_object(game_1_2, ScoreAlgorithm.LCS)
    # this means that warrior_1 was totaly erased, and warrior_2 totally preserved
    assert score.score_for(battle.warrior_1_id) == 0

    # second game - warrior_2 || warrior_1
    assert battle.score_object(game_2_1, ScoreAlgorithm.LCS).score_for(battle.warrior_2_id) == 1

    assert battle.warrior_score(battle.warrior_1_id) == 0

    # to compute performance we must assign warrior_arenas (not in the db)
    warrior_arena_1 = WarriorArenaFactory(warrior=battle.warrior_1, rating_playstyle=[0, 0])
    warrior_arena_2 = WarriorArenaFactory(warrior=battle.warrior_2, rating_playstyle=[0, 0])
    # it could have been closer to 1 if there was a discrepancy in the ratings
    assert battle.warrior_performance(warrior_arena_1, warrior_arena_2) == pytest.approx(-0.5, abs=0.01)


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
    ('warrior_slot', 'similarities'),
    (
        ('warrior_1', (0.1, 0.3)),
        ('warrior_2', (0.2, 0.4)),
    ),
)
def test_a_score_names_the_warrior_it_measures(scored_battle, warrior_slot, similarities):
    """
    A similarity belongs to a warrior, not to a slot:
    the same warrior leads one game and follows in the other,
    so asking by name is the only question with one answer.
    """
    warrior_id = getattr(scored_battle, f'{warrior_slot}_id')
    assert tuple(
        scored_battle.score_object(game, ScoreAlgorithm.LCS).similarity_for(warrior_id)
        for game in scored_battle.games_list
    ) == similarities


@pytest.mark.django_db
def test_battle_scores_of_both_warriors_sum_to_one(scored_battle):
    """
    The two warriors of a battle split one outcome between them.
    Selecting a game and naming its warriors are separate steps,
    and getting one right while the other is wrong
    leaves the pair summing to something other than 1.
    """
    assert (
        scored_battle.warrior_score(scored_battle.warrior_1_id) +
        scored_battle.warrior_score(scored_battle.warrior_2_id)
    ) == pytest.approx(1)


@pytest.mark.django_db
def test_battle_score_pends_until_every_game_is_scored():
    """
    A one-game mean and a two-game mean do not measure the same thing,
    so a battle mid-resolution has no score at all;
    rating admits the battle by the same rule.
    """
    battle = BattleFactory()
    GameScoreFactory(
        battle=battle,
        direction='1_2',
        algorithm=ScoreAlgorithm.LCS,
        warrior_1_similarity=0.1,
        warrior_2_similarity=0.2,
    )
    assert battle.warrior_score(battle.warrior_1_id) is None


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
            for battle in Battle.objects.prefetch_related('games', 'game_scores__game'):
                battle.warrior_score(warrior.id)
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


def resolve_game(battle, direction, resolved_at):
    game = game_of(battle, direction)
    game.resolved_at = resolved_at
    game.save(update_fields=['resolved_at'])


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('resolved_directions', 'is_resolved'),
    (
        (('1_2', '2_1'), True),
        (('1_2',), False),
        (('2_1',), False),
        ((), False),
    ),
)
def test_resolved_needs_every_game(resolved_directions, is_resolved):
    battle = BattleFactory()
    for direction in resolved_directions:
        resolve_game(battle, direction, timezone.now())
    assert (battle in Battle.objects.resolved()) is is_resolved


@pytest.mark.django_db
def test_resolved_reads_the_games_not_the_columns():
    """
    The game row is the record and the battle's column is its mirror,
    so a stale column does not make a battle resolved.
    """
    battle = BattleFactory(
        resolved_at_1_2=timezone.now(),
        resolved_at_2_1=timezone.now(),
    )
    resolve_game(battle, '2_1', None)
    assert battle not in Battle.objects.resolved()
