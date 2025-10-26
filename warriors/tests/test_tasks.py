from unittest import mock

import httpx
import openai
import pytest
from django.utils import timezone
from django_goals.models import AllDone, RetryMeLater

from ..tasks import (
    do_moderation, openai_client, resolve_battle, schedule_battle_top_arena,
    transfer_rating,
)
from ..warriors import MAX_WARRIOR_LENGTH


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

    do_moderation(None, warrior.id)

    warrior.refresh_from_db()
    assert warrior.moderation_date is not None
    assert warrior.moderation_passed is (not moderation_flagged)
    assert warrior.moderation_model == 'moderation-asdf'


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{'rating': 100}], indirect=True)
@pytest.mark.parametrize('other_warrior_arena', [{'rating': 250}], indirect=True)
def test_schedule_battle_top(warrior_arena, other_warrior_arena, arena, monkeypatch):
    monkeypatch.setattr('random.random', lambda: 0.9999)
    battle = schedule_battle_top_arena(str(arena.id))
    assert battle is not None
    assert {warrior_arena.warrior, other_warrior_arena.warrior} == {battle.warrior_1, battle.warrior_2}


@pytest.mark.django_db
def test_resolve_battle(arena, battle, monkeypatch):
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
    assert battle.text_unit_2_1.content == 'Some result'
    assert battle.finish_reason_2_1 == 'stop'
    assert battle.resolved_at_2_1 is not None
    assert battle.llm_version_2_1 == 'gpt-3.5/1234'
    assert battle.lcs_len_2_1_1 == 23
    assert battle.lcs_len_2_1_2 == 14


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{'attempts_2_1': 10}], indirect=True)
def test_resolve_battle_service_unavailable(battle, monkeypatch):
    create_mock = mock.Mock(side_effect=openai.APIStatusError(
        'not now',
        response=httpx.Response(503, request=httpx.Request('POST', 'https://openai.com')),
        body=None,
    ))
    monkeypatch.setattr(openai_client.chat.completions, 'create', create_mock)

    resolve_battle(battle.id, '2_1')

    # DB state is correct
    battle.refresh_from_db()
    assert battle.finish_reason_2_1 == 'error'
    assert battle.resolved_at_2_1 is not None


@pytest.mark.django_db
def test_resolve_battle_rate_limit(battle, monkeypatch):
    create_mock = mock.Mock(side_effect=openai.RateLimitError(
        'Rate limit bro',
        response=httpx.Response(429, request=httpx.Request('POST', 'https://openai.com')),
        body=None,
    ))
    monkeypatch.setattr(openai_client.chat.completions, 'create', create_mock)

    ret = resolve_battle(battle.id, '2_1')
    assert isinstance(ret, RetryMeLater)

    # DB state is correct
    battle.refresh_from_db()
    assert battle.finish_reason_2_1 == ''
    assert battle.resolved_at_2_1 is None


@pytest.mark.django_db
def test_resolve_battle_character_limit(battle, monkeypatch):
    completion_mock = mock.MagicMock()
    completion_mock.message.content = 'Some result' * 100
    completion_mock.finish_reason = 'stop'
    completions_mock = mock.MagicMock()
    completions_mock.choices = [completion_mock]
    completions_mock.model = 'gpt-3.5'
    completions_mock.system_fingerprint = '1234'
    create_mock = mock.Mock(return_value=completions_mock)
    monkeypatch.setattr(openai_client.chat.completions, 'create', create_mock)

    resolve_battle(battle.id, '1_2')

    # DB state is correct
    battle.refresh_from_db()
    assert battle.finish_reason_1_2 == 'character_limit'
    assert battle.resolved_at_1_2 is not None
    assert len(battle.text_unit_1_2.content) == MAX_WARRIOR_LENGTH


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
    transfer_rating(None, battle.id)


@pytest.mark.django_db
@pytest.mark.real_world
@pytest.mark.parametrize('warrior', [{
    'name': 'Integration Test Warrior',
    'author_name': 'Integration Test Author',
}], indirect=True)
def test_do_moderation_real_endpoint(warrior):
    assert warrior.body
    assert warrior.moderation_date is None

    # Call the real moderation endpoint
    result = do_moderation(None, warrior.id)

    # Verify the result is AllDone
    assert isinstance(result, AllDone)

    # Verify the warrior was updated
    warrior.refresh_from_db()
    assert warrior.moderation_date is not None
    assert warrior.moderation_passed is not None
    assert warrior.moderation_model == 'omni-moderation-latest'
