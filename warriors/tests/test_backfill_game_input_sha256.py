import pytest
from django.core.management import call_command

from .test_verify_games import create_mirrored_battle


@pytest.mark.django_db
def test_backfill_fills_both_directions():
    battle = create_mirrored_battle()
    battle.games.all().update(input_sha256=None)

    call_command('backfill_game_input_sha256', batch_size=1)

    game_1_2 = battle.games.get(warrior_1=battle.warrior_1)
    game_2_1 = battle.games.get(warrior_1=battle.warrior_2)
    # each direction takes its own column, not the pair's first one
    assert bytes(game_1_2.input_sha256) == battle.input_sha256_1_2
    assert bytes(game_2_1.input_sha256) == battle.input_sha256_2_1


@pytest.mark.django_db
def test_backfill_leaves_rows_with_no_source_blank():
    battle = create_mirrored_battle()
    battle.games.all().update(input_sha256=None)
    battle.input_sha256_1_2 = None
    battle.save(update_fields=['input_sha256_1_2'])

    call_command('backfill_game_input_sha256')

    # writing null over null would only make dead tuples
    game_1_2 = battle.games.get(warrior_1=battle.warrior_1)
    assert game_1_2.input_sha256 is None
