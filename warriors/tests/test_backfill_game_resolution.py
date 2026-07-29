import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from .test_verify_games import create_mirrored_battle


def blank_the_mirror(battle):
    """The state the old resolver left when it skipped the mirror."""
    battle.games.all().update(
        text_unit=None,
        finish_reason='',
        llm_version='',
        resolved_at=None,
    )


@pytest.mark.django_db
def test_fills_each_direction_from_its_own_columns():
    battle = create_mirrored_battle()
    blank_the_mirror(battle)

    call_command('backfill_game_resolution', batch_size=1)

    # the swapped warrior pair is the one thing the two statements can
    # get wrong; which fields they carry is the audit's business below
    game_1_2 = battle.games.get(warrior_1=battle.warrior_1)
    game_2_1 = battle.games.get(warrior_1=battle.warrior_2)
    assert game_1_2.text_unit_id == battle.text_unit_1_2_id
    assert game_2_1.text_unit_id == battle.text_unit_2_1_id


@pytest.mark.django_db
def test_leaves_nothing_for_the_audit():
    battle = create_mirrored_battle()
    blank_the_mirror(battle)
    # the blanks are what the audit reports, and what blocks the column drop
    with pytest.raises(CommandError):
        call_command('verify_games')

    call_command('backfill_game_resolution')

    call_command('verify_games')


@pytest.mark.django_db
def test_leaves_an_unresolved_direction_alone():
    battle = create_mirrored_battle()
    blank_the_mirror(battle)
    battle.resolved_at_1_2 = None
    battle.attempts_1_2 = 3
    battle.save(update_fields=['resolved_at_1_2', 'attempts_1_2'])

    call_command('backfill_game_resolution')

    # a direction still retrying has its attempts written under us;
    # resolution mirrors the whole result when it lands
    game_1_2 = battle.games.get(warrior_1=battle.warrior_1)
    assert game_1_2.resolved_at is None
    assert game_1_2.attempts == 0


@pytest.mark.django_db
def test_leaves_a_resolved_game_alone():
    battle = create_mirrored_battle()
    game_1_2 = battle.games.get(warrior_1=battle.warrior_1)
    game_1_2.finish_reason = 'character_limit'
    game_1_2.save(update_fields=['finish_reason'])

    call_command('backfill_game_resolution')

    # a resolved row disagreeing with its battle is a bug for verify_games
    # to report, not data for a repair to paper over
    game_1_2.refresh_from_db()
    assert game_1_2.finish_reason == 'character_limit'
