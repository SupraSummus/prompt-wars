import pytest
from django.core.management import call_command
from django.utils import timezone

from ..rankings import Ranking
from .factories import BattleFactory, WarriorRatingFactory
from .fixtures import create_scores


@pytest.mark.django_db
def test_refit_ratings_refits_a_rating_nothing_marked_stale(capsys):
    """A rating whose battles changed but whose error says nothing still gets refit."""
    winner, loser = WarriorRatingFactory(), WarriorRatingFactory()
    now = timezone.now()
    battle = BattleFactory(
        warrior_1=winner.warrior,
        warrior_2=loser.warrior,
        game_1_2__resolved_at=now,
        game_2_1__resolved_at=now,
    )
    # canonical order decides who leads; score so that `winner` wins either way
    if battle.warrior_1_id == winner.warrior_id:
        create_scores(battle, 1, 0.1, 1, 0.1, algorithm=Ranking.LCS.score_algorithm)
    else:
        create_scores(battle, 0.1, 1, 0.1, 1, algorithm=Ranking.LCS.score_algorithm)
    assert (winner.rating_error, loser.rating_error) == (0.0, 0.0)

    call_command('refit_ratings')

    winner.refresh_from_db()
    loser.refresh_from_db()
    assert winner.rating > loser.rating
    assert capsys.readouterr().out.strip().endswith(f'refit {2 * len(Ranking)} ratings')
