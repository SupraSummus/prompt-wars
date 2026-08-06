import pytest
from django.core.management import call_command

from ..score import GameScore
from .factories import game_of
from .fixtures import create_scores
from .test_verify_games import create_mirrored_battle


@pytest.mark.django_db
def test_backfill_links_each_score_to_its_own_game():
    # two battles, because the join has to pick the game row by battle
    # as well as by direction
    battles = [create_mirrored_battle() for _ in range(2)]
    for battle in battles:
        create_scores(battle, 1, 0.1, 1, 0.1)
    GameScore.objects.update(game=None)

    # no --batch-pages: these scores share a page, so nothing splits them
    call_command('backfill_game_score_game')

    for battle in battles:
        for score in battle.game_scores.all():
            assert score.game == game_of(battle, score.direction)
