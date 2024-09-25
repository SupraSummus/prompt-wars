import datetime
from unittest import mock

import httpx
import openai
import pytest
from django.utils import timezone
from django_goals.models import RetryMeLater

from ..models import MAX_WARRIOR_LENGTH, Battle, WarriorArena
from ..tasks import (
    do_moderation, openai_client, resolve_battle, schedule_battle,
    schedule_battle_top_arena, schedule_battles, transfer_rating,
    update_rating,
)
from .factories import WarriorArenaFactory


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{
    'name': 'Test Warrior',
    'author_name': 'Test Author',
}], indirect=True)
@pytest.mark.parametrize('moderation_flagged', [True, False])
def test_do_moderation(warrior_arena, monkeypatch, moderation_flagged):
    assert warrior_arena.body

    moderation_result_mock = mock.MagicMock()
    moderation_result_mock.flagged = moderation_flagged
    moderation_mock = mock.MagicMock()
    moderation_mock.return_value.model = 'moderation-asdf'
    moderation_mock.return_value.results = [moderation_result_mock]
    monkeypatch.setattr(openai_client.moderations, 'create', moderation_mock)

    do_moderation(None, warrior_arena.id)

    warrior_arena.refresh_from_db()
    assert warrior_arena.moderation_date is not None
    assert warrior_arena.moderation_passed is (not moderation_flagged)
    assert warrior_arena.moderation_model == 'moderation-asdf'


@pytest.mark.django_db
def test_schedule_battles_empty():
    assert not WarriorArena.objects.exists()
    schedule_battles()


@pytest.mark.django_db
def test_schedule_battles_no_match(warrior_arena):
    schedule_battles()
    assert not Battle.objects.exists()


@pytest.mark.django_db
def test_schedule_battles(arena):
    warriors = set(WarriorArenaFactory.create_batch(
        3,
        arena=arena,
        next_battle_schedule=timezone.now(),
    ))
    schedule_battles()
    participants = set()
    for b in Battle.objects.all():
        participants.add(b.warrior_1)
        participants.add(b.warrior_2)
    assert participants == warriors


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
@pytest.mark.parametrize('other_warrior_arena', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle(arena, warrior_arena, other_warrior_arena):
    now = datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    assert warrior_arena.next_battle_schedule is not None
    assert other_warrior_arena.next_battle_schedule is not None

    schedule_battle(now=now)

    battle = Battle.objects.get()
    assert battle.arena == arena

    warrior_arena.refresh_from_db()
    # it advances the next_battle_schedule
    assert warrior_arena.next_battle_schedule > now


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{
    'next_battle_schedule': datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
}], indirect=True)
def test_schedule_battle_no_warriors(warrior_arena):
    now = datetime.datetime(2022, 1, 2, 0, 0, 0, tzinfo=datetime.timezone.utc)
    schedule_battle(now)

    assert not Battle.objects.exists()

    # next_battle_schedule is moved to the future
    warrior_arena.refresh_from_db()
    assert warrior_arena.next_battle_schedule > now


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{'rating': 100}], indirect=True)
@pytest.mark.parametrize('other_warrior_arena', [{'rating': 250}], indirect=True)
def test_schedule_battle_top(warrior_arena, other_warrior_arena, arena, monkeypatch):
    monkeypatch.setattr('random.random', lambda: 0.9999)
    battle = schedule_battle_top_arena(str(arena.id))
    assert battle is not None
    assert {warrior_arena, other_warrior_arena} == {battle.warrior_1, battle.warrior_2}


@pytest.mark.django_db
@pytest.mark.parametrize('arena', [
    {'prompt': 'arena specific prompt'},
    {'prompt': ''},
], indirect=True)
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
    if arena.prompt:
        assert create_mock.call_args.kwargs['messages'] == [{
            'role': 'system',
            'content': arena.prompt,
        }, {
            'role': 'user',
            'content': battle.warrior_2.body + battle.warrior_1.body,
        }]
    else:
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
def test_resolve_battle_bad_request(battle, monkeypatch):
    create_mock = mock.Mock(side_effect=openai.APIStatusError(
        'Bad request bro',
        response=httpx.Response(400, request=httpx.Request('POST', 'https://openai.com')),
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
    assert len(battle.result_1_2) == MAX_WARRIOR_LENGTH


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
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'lcs_len_1_2_1': 31,
    'lcs_len_1_2_2': 32,
    'resolved_at_2_1': timezone.now(),
    'lcs_len_2_1_1': 23,
    'lcs_len_2_1_2': 18,
}], indirect=True)
@pytest.mark.parametrize('warrior_arena', [{
    'rating_playstyle': [0, 0],
    'rating_error': 1,
}], indirect=True)
@pytest.mark.parametrize('other_warrior_arena', [{
    'rating_playstyle': [0, 0],
    'rating_error': -1,
}], indirect=True)
def test_update_rating(warrior_arena, other_warrior_arena, battle):
    WarriorArenaFactory.create_batch(3, rating_error=0)  # distraction
    assert warrior_arena.rating == 0.0
    assert other_warrior_arena.rating == 0.0

    update_rating(n=2)

    warrior_arena.refresh_from_db()
    other_warrior_arena.refresh_from_db()
    assert warrior_arena.rating != 0.0
    assert other_warrior_arena.rating != 0.0
    assert warrior_arena.rating_error == pytest.approx(0, abs=0.01)
    assert other_warrior_arena.rating_error == pytest.approx(0.0, abs=0.01)
    assert warrior_arena.rating + other_warrior_arena.rating == pytest.approx(0.0, abs=0.01)
