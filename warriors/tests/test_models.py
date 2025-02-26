import datetime
from uuid import UUID

import pytest
from django.utils import timezone

from ..battles import Battle, BattleViewpoint
from ..text_unit import TextUnit
from .factories import BattleFactory, WarriorArenaFactory


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{'rating': 0.0}], indirect=True)
@pytest.mark.parametrize(('other_warrior_arena', 'matched'), [
    ({'rating': 2}, False),
    ({'rating': 1.2}, False),
    ({'rating': -1.2}, False),
    ({'rating': 0}, True),
    ({'rating': 1}, True),
    ({'rating': -1}, True),
], indirect=['other_warrior_arena'])
def test_find_opponents_max_rating_diff(warrior_arena, other_warrior_arena, matched):
    opponents = warrior_arena.find_opponents(max_rating_diff=1.2)
    assert (other_warrior_arena in opponents) is matched


@pytest.mark.django_db
@pytest.mark.parametrize('other_warrior', [
    {'moderation_passed': False},
    {'moderation_passed': None},
], indirect=True)
def test_find_opponents_exclude_not_worthy(warrior_arena, other_warrior_arena):
    opponents = warrior_arena.find_opponents()
    assert other_warrior_arena not in opponents


@pytest.mark.django_db
@pytest.mark.parametrize('battle_exists', [True, False])
def test_find_opponents_exclude_already_battled(warrior_arena, other_warrior_arena, battle_exists):
    if battle_exists:
        Battle.create_from_warriors(warrior_arena, other_warrior_arena)
    opponents = warrior_arena.find_opponents()
    opponent_expected = not battle_exists
    assert (other_warrior_arena in opponents) is opponent_expected


@pytest.mark.django_db
def test_create_battle_lots_of_games_played(warrior_arena, battle, other_warrior_arena):
    BattleFactory.create_batch(
        100,
        arena=battle.arena,
        llm=battle.llm,
        warrior_1=battle.warrior_1,
        warrior_2=battle.warrior_2,
    )
    warrior_arena.create_battle(other_warrior_arena)
    warrior_arena.refresh_from_db()
    assert warrior_arena.games_played == 102  # 1 from fixture, 100 created in this test, 1 created in create_battle
    assert warrior_arena.next_battle_schedule > timezone.now() + datetime.timedelta(days=365 * 10)

    # opponent has games_played recalculated
    other_warrior_arena.refresh_from_db()
    assert other_warrior_arena.games_played == 102


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('warrior_arena', 'min_delay_minutes', 'max_delay_minutes'),
    [
        ({'games_played': 0}, 0, 0),
        ({'games_played': 1}, 0, 1),
        ({'games_played': 2}, 1, 3),
        ({'games_played': 3}, 3, 7),
        ({'games_played': 4}, 7, 15),
    ],
    indirect=['warrior_arena'],
)
def test_next_battle_delay(warrior_arena, min_delay_minutes, max_delay_minutes):
    delay = warrior_arena.get_next_battle_delay()
    assert delay >= datetime.timedelta(minutes=min_delay_minutes)
    assert delay <= datetime.timedelta(minutes=max_delay_minutes)


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
