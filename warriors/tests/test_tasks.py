import datetime
from unittest import mock

import pytest
from django.utils import timezone

from ..models import Battle, Warrior
from ..tasks import (
    do_moderation, openai_client, resolve_battle, schedule_battles,
    transfer_rating,
)
from .factories import BattleFactory, WarriorFactory


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'name': 'Test Warrior',
    'author_name': 'Test Author',
}], indirect=True)
@pytest.mark.parametrize('moderation_flagged', [True, False])
def test_do_moderation(warrior, monkeypatch, moderation_flagged):
    assert warrior.body

    moderation_result_mock = mock.MagicMock()
    moderation_result_mock.flagged = moderation_flagged
    moderation_mock = mock.MagicMock()
    moderation_mock.return_value.model = 'moderation-asdf'
    moderation_mock.return_value.results = [moderation_result_mock]
    monkeypatch.setattr(openai_client.moderations, 'create', moderation_mock)

    do_moderation(warrior.id)

    warrior.refresh_from_db()
    assert warrior.moderation_date is not None
    assert warrior.moderation_passed is (not moderation_flagged)
    assert warrior.moderation_model == 'moderation-asdf'
    assert (warrior.next_battle_schedule is None) == moderation_flagged


@pytest.mark.django_db
def test_schedule_battles_empty():
    assert not Warrior.objects.exists()
    schedule_battles()


@pytest.mark.django_db
def test_schedule_battles_no_match(warrior):
    schedule_battles()
    assert not Battle.objects.exists()


@pytest.mark.django_db
def test_schedule_battles():
    warriors = set(WarriorFactory.create_batch(
        3,
        next_battle_schedule=timezone.now(),
    ))
    schedule_battles()
    participants = set()
    for b in Battle.objects.all():
        participants.add(b.warrior_1)
        participants.add(b.warrior_2)
    assert participants == warriors


@pytest.mark.django_db
def test_resolve_battle(battle, monkeypatch):
    assert battle.warrior_1.body
    assert battle.warrior_2.body

    completion_mock = mock.MagicMock()
    completion_mock.message.content = 'Some result'
    completion_mock.finish_reason = 'stop'
    completions_mock = mock.MagicMock()
    completions_mock.choices = [completion_mock]
    completions_mock.model = 'gpt-3.5'
    completions_mock.system_fingerprint = '1234'
    create_mock = mock.Mock(return_value=completions_mock)
    monkeypatch.setattr(openai_client.chat.completions, 'create', create_mock)

    lcs_len_mock = mock.MagicMock()
    lcs_len_mock.side_effect = [14, 23]
    monkeypatch.setattr('warriors.tasks.lcs_len', lcs_len_mock)

    resolve_battle(battle.id, '2_1')

    # LLM was properly invoked
    assert create_mock.call_count == 1
    assert create_mock.call_args.kwargs['messages'] == [{
        'role': 'user',
        'content': battle.warrior_2.body + battle.warrior_1.body,
    }]

    # lcs_len was properly invoked
    assert lcs_len_mock.call_count == 2
    assert lcs_len_mock.call_args_list[0].args == (battle.warrior_2.body, 'Some result')
    assert lcs_len_mock.call_args_list[1].args == (battle.warrior_1.body, 'Some result')

    # DB state is correct
    battle.refresh_from_db()
    assert battle.result_2_1 == 'Some result'
    assert battle.finish_reason_2_1 == 'stop'
    assert battle.resolved_at_2_1 is not None
    assert battle.llm_version_2_1 == 'gpt-3.5/1234'
    assert battle.lcs_len_2_1_1 == 23
    assert battle.lcs_len_2_1_2 == 14


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'lcs_len_1_2_1': 31,
    'lcs_len_1_2_2': 31,
    'resolved_at_2_1': timezone.now(),
    'lcs_len_2_1_1': 31,
    'lcs_len_2_1_2': 31,
}], indirect=True)
def test_transfer_rating(battle):
    assert battle.warrior_1.next_battle_schedule is None
    assert battle.warrior_2.next_battle_schedule is None

    transfer_rating(battle.id)
    battle.refresh_from_db()
    assert battle.rating_transferred_at is not None

    # warriors are put back into matchmaking queue
    assert battle.warrior_1.next_battle_schedule is not None
    assert battle.warrior_2.next_battle_schedule is not None


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'lcs_len_1_2_1': 31,
    'lcs_len_1_2_2': 31,
    'resolved_at_2_1': timezone.now(),
    'lcs_len_2_1_1': 31,
    'lcs_len_2_1_2': 31,
}], indirect=True)
def test_transfer_rating_lots_of_games_played(battle, warrior):
    BattleFactory.create_batch(
        100,
        warrior_1=battle.warrior_1,
        warrior_2=battle.warrior_2,
        resolved_at_1_2=timezone.now(),
        lcs_len_1_2_1=31,
        lcs_len_1_2_2=31,
        resolved_at_2_1=timezone.now(),
        lcs_len_2_1_1=31,
        lcs_len_2_1_2=31,
    )
    transfer_rating(battle.id)
    warrior.refresh_from_db()
    assert warrior.games_played == 101
    assert warrior.next_battle_schedule > timezone.now() + datetime.timedelta(days=365 * 10)
