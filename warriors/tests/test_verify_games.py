import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from ..battles import LLM, DBGame, mirrored_game_fields
from .factories import BattleFactory, TextUnitFactory, WarriorFactory


@pytest.fixture
def mirrored_battle():
    now = timezone.now()
    # the warrior_ordering check constraint wants the canonical pair order
    warrior_1, warrior_2 = sorted(
        [WarriorFactory(), WarriorFactory()],
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
    # every field compares equal, so no CommandError and nothing created —
    # the guard against false alarms like memoryview-vs-bytes on a bytea
    call_command('verify_games')

    assert mirrored_battle.games.count() == 2


@pytest.mark.django_db
def test_verify_creates_missing_game(mirrored_battle):
    mirrored_battle.games.filter(warrior_1=mirrored_battle.warrior_2).delete()

    call_command('verify_games', batch_size=1)

    game = mirrored_battle.games.get(warrior_1=mirrored_battle.warrior_2)
    assert game.warrior_2_id == mirrored_battle.warrior_1_id
    assert game.llm == mirrored_battle.llm
    assert game.scheduled_at == mirrored_battle.scheduled_at
    assert bytes(game.input_sha256) == mirrored_battle.input_sha256_2_1
    assert game.text_unit_id == mirrored_battle.text_unit_2_1_id
    assert game.finish_reason == mirrored_battle.finish_reason_2_1
    assert game.llm_version == mirrored_battle.llm_version_2_1
    assert game.resolved_at == mirrored_battle.resolved_at_2_1
    assert game.attempts == mirrored_battle.attempts_2_1


@pytest.mark.django_db
def test_verify_reports_drifted_game(mirrored_battle):
    game = mirrored_battle.games.get(warrior_1=mirrored_battle.warrior_1)
    game.finish_reason = 'character_limit'
    game.save(update_fields=['finish_reason'])

    with pytest.raises(CommandError):
        call_command('verify_games')

    # the battle is the authoritative writer, so the row is left alone
    game.refresh_from_db()
    assert game.finish_reason == 'character_limit'


@pytest.mark.django_db
def test_verify_reports_game_outside_the_pair(mirrored_battle):
    game = mirrored_battle.games.get(warrior_1=mirrored_battle.warrior_1)
    game.warrior_1 = WarriorFactory()
    game.save(update_fields=['warrior_1'])

    with pytest.raises(CommandError):
        call_command('verify_games')

    # the missing direction is created, the stray row is only reported
    assert mirrored_battle.games.filter(warrior_1=mirrored_battle.warrior_1).exists()
    assert DBGame.objects.filter(id=game.id).exists()
