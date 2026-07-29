import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from ..battles import LLM, DBGame, mirrored_game_fields
from .factories import BattleFactory, TextUnitFactory, WarriorFactory


@pytest.fixture
def mirrored_battle():
    return create_mirrored_battle()


def create_mirrored_battle():
    now = timezone.now()
    # the warrior_ordering check constraint wants the canonical pair order
    warrior_1, warrior_2 = sorted(
        WarriorFactory.create_batch(2),
        key=lambda warrior: warrior.id,
    )
    battle = BattleFactory(
        llm=LLM.OPENAI_GPT,
        warrior_1=warrior_1,
        warrior_2=warrior_2,
        resolved_at_1_2=now,
        text_unit_1_2=TextUnitFactory(),
        finish_reason_1_2='stop',
        llm_version_1_2='gpt-3.5/1234',
        input_sha256_1_2=b'\x01' * 32,
        resolved_at_2_1=now,
        text_unit_2_1=TextUnitFactory(),
        finish_reason_2_1='stop',
        llm_version_2_1='gpt-3.5/1234',
        input_sha256_2_1=b'\x02' * 32,
    )
    for direction in ('1_2', '2_1'):
        DBGame.objects.create(
            battle=battle,
            **mirrored_game_fields(battle, direction),
        )
    return battle


@pytest.mark.django_db
def test_verify_accepts_a_faithful_pair(mirrored_battle):
    # every field compares equal, so no CommandError —
    # the guard against false alarms like memoryview-vs-bytes on a bytea
    call_command('verify_games')


@pytest.mark.django_db
def test_verify_reports_a_missing_game(mirrored_battle):
    # create_from_warriors writes a battle and both games in one
    # transaction, so a row missing now is a broken invariant
    mirrored_battle.games.filter(warrior_1=mirrored_battle.warrior_2).delete()

    with pytest.raises(CommandError, match='missing game row: 1'):
        call_command('verify_games', batch_size=1)


@pytest.mark.django_db
def test_verify_reports_a_blank_field(mirrored_battle):
    game = mirrored_battle.games.get(warrior_1=mirrored_battle.warrior_1)
    game.input_sha256 = None
    game.save(update_fields=['input_sha256'])

    with pytest.raises(CommandError, match='blank input_sha256: 1'):
        call_command('verify_games')

    # read-only: filling this is backfill_game_input_sha256's job
    game.refresh_from_db()
    assert game.input_sha256 is None


@pytest.mark.django_db
def test_verify_reports_a_conflicting_field(mirrored_battle):
    game = mirrored_battle.games.get(warrior_1=mirrored_battle.warrior_1)
    game.finish_reason = 'character_limit'
    game.save(update_fields=['finish_reason'])

    with pytest.raises(CommandError, match='conflicting finish_reason: 1'):
        call_command('verify_games')


@pytest.mark.django_db
def test_verify_summarizes_each_category_once(mirrored_battle):
    # one bad backfill drifts every battle in the table, so the report
    # counts a category instead of listing it — the single odd row has
    # to stay findable next to the mass one
    other_battle = create_mirrored_battle()
    for battle in (mirrored_battle, other_battle):
        battle.games.all().update(finish_reason='character_limit')

    with pytest.raises(CommandError) as error:
        call_command('verify_games')

    report = str(error.value)
    assert 'conflicting finish_reason: 4' in report
    assert len([
        line for line in report.splitlines()
        if 'finish_reason' in line
    ]) == 1


@pytest.mark.django_db
def test_verify_leaves_an_unresolved_direction_alone(mirrored_battle):
    # attempts climbs while the direction retries, so a difference here
    # is in-flight state, not drift — comparing it would cry wolf
    mirrored_battle.resolved_at_1_2 = None
    mirrored_battle.attempts_1_2 = 3
    mirrored_battle.save(update_fields=['resolved_at_1_2', 'attempts_1_2'])

    call_command('verify_games')


@pytest.mark.django_db
def test_verify_reports_game_outside_the_pair(mirrored_battle):
    game = mirrored_battle.games.get(warrior_1=mirrored_battle.warrior_1)
    game.warrior_1 = WarriorFactory()
    game.save(update_fields=['warrior_1'])

    with pytest.raises(CommandError, match='outside the battle pair: 1'):
        call_command('verify_games')
