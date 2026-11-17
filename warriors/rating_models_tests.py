import datetime
import random

import pytest
from django.utils import timezone

from .battles import LLM
from .rankings import Ranking
from .rating_models import WarriorRating, enter_ladder, update_rating
from .tests.factories import (
    BattleFactory, WarriorFactory, WarriorRatingFactory, batch_create_battles,
)
from .tests.fixtures import create_scores


@pytest.mark.django_db
def test_update_rating_takes_newer_battles(battle, warrior_rating, other_warrior_rating):
    then = timezone.now() - datetime.timedelta(days=10)
    # warrior_2 won the first battle
    battle.scheduled_at = then
    battle.save()
    battle.games.update(scheduled_at=then, resolved_at=then)
    create_scores(battle, 0, 1, 0, 1)

    # warrior_1 won the second battle
    new_then = then + datetime.timedelta(days=1)
    new_battle = BattleFactory(
        warrior_1=battle.warrior_1,
        warrior_2=battle.warrior_2,
        scheduled_at=new_then,
        game_1_2__resolved_at=new_then,
        game_2_1__resolved_at=new_then,
    )
    create_scores(new_battle, 1, 0, 1, 0)
    rating_1 = WarriorRating.objects.get(warrior=battle.warrior_1, ranking=Ranking.LCS)
    rating_2 = WarriorRating.objects.get(warrior=battle.warrior_2, ranking=Ranking.LCS)

    rating_1.update_rating()

    rating_1.refresh_from_db()
    rating_2.refresh_from_db()
    assert rating_1.rating > rating_2.rating


@pytest.mark.django_db
def test_each_ranking_rates_by_its_own_algorithm():
    """One battle, two rankings: each reads the battle through its own score algorithm."""
    now = timezone.now()
    # sorted here, not left to the factory:
    # the assertions below name these warriors,
    # and create_scores scores them by the battle's order
    warrior_1, warrior_2 = sorted(
        WarriorFactory.create_batch(2),
        key=lambda warrior: warrior.id,
    )
    battle = BattleFactory(
        warrior_1=warrior_1,
        warrior_2=warrior_2,
        game_1_2__resolved_at=now,
        game_2_1__resolved_at=now,
    )
    create_scores(battle, 1, 0.1, 1, 0.1, algorithm=Ranking.LCS.score_algorithm)
    create_scores(battle, 0.1, 1, 0.1, 1, algorithm=Ranking.SEMANTIC.score_algorithm)

    for ranking in Ranking:
        for warrior in (warrior_1, warrior_2):
            WarriorRatingFactory(warrior=warrior, ranking=ranking)
    for _ in range(2):
        for warrior_rating in WarriorRating.objects.order_by('id'):
            warrior_rating.update_rating()

    def rating(warrior, ranking):
        return WarriorRating.objects.get(warrior=warrior, ranking=ranking).rating

    assert rating(warrior_1, Ranking.LCS) > 40
    assert rating(warrior_1, Ranking.LCS) == -rating(warrior_2, Ranking.LCS)
    assert rating(warrior_2, Ranking.SEMANTIC) > 40
    assert rating(warrior_2, Ranking.SEMANTIC) == -rating(warrior_1, Ranking.SEMANTIC)


@pytest.mark.django_db
def test_rating_reads_battles_of_every_model(warrior_rating):
    """The ladder is one pool: a battle counts whichever model was drawn for it."""
    now = timezone.now()
    for llm in LLM:
        battle = BattleFactory(
            llm=llm,
            warrior_1=warrior_rating.warrior,
            warrior_2=WarriorFactory(),
            game_1_2__resolved_at=now,
            game_2_1__resolved_at=now,
        )
        create_scores(battle, 1, 0.1, 1, 0.1)

    warrior_rating.update_rating()

    warrior_rating.refresh_from_db()
    assert warrior_rating.games_played == len(LLM)


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'game_1_2__resolved_at': timezone.now(),
    'game_2_1__resolved_at': timezone.now(),
}], indirect=True)
@pytest.mark.parametrize('warrior_rating', [{
    'rating_playstyle': [0, 0],
    'rating_error': 1,
}], indirect=True)
@pytest.mark.parametrize('other_warrior_rating', [{
    'rating_playstyle': [0, 0],
    'rating_error': -1,
}], indirect=True)
def test_update_rating(warrior_rating, other_warrior_rating, battle):
    create_scores(battle, 0.31, 0.32, 0.23, 0.18)

    WarriorRatingFactory.create_batch(3, rating_error=0)  # distraction
    assert warrior_rating.rating == 0.0
    assert other_warrior_rating.rating == 0.0

    update_rating(n=2)

    warrior_rating.refresh_from_db()
    other_warrior_rating.refresh_from_db()
    assert warrior_rating.rating != 0.0
    assert other_warrior_rating.rating != 0.0
    assert warrior_rating.rating_error == pytest.approx(0, abs=0.02)
    assert other_warrior_rating.rating_error == pytest.approx(0.0, abs=0.02)
    assert warrior_rating.rating + other_warrior_rating.rating == pytest.approx(0.0, abs=0.02)


@pytest.mark.django_db
def test_enter_ladder(warrior):
    """A warrior off the ladder gets its clock and a rating in every ranking; a second entry changes nothing."""
    warrior.next_battle_schedule = None
    warrior.save(update_fields=['next_battle_schedule'])
    warrior.ratings.all().delete()

    enter_ladder(warrior)
    clock = warrior.next_battle_schedule
    enter_ladder(warrior)

    warrior.refresh_from_db()
    assert warrior.next_battle_schedule == clock is not None
    assert sorted(warrior.ratings.values_list('ranking', flat=True)) == sorted(Ranking)


@pytest.mark.django_db
def test_update_rating_does_little_db_hits(warrior_rating, django_assert_max_num_queries):
    n = 100
    battles = batch_create_battles(warrior_rating.warrior, n)
    for battle in battles:
        create_scores(battle, random.random(), random.random(), random.random(), random.random())
    with django_assert_max_num_queries(n // 2):
        warrior_rating.update_rating()
    warrior_rating.refresh_from_db()
    assert warrior_rating.games_played == n
