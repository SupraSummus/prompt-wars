from unittest import mock

import anthropic
import pytest

from ..battles import LLM
from ..tasks import resolve_battle
from .anthropic import resolve_battle as anthropic_resolve_battle


@pytest.fixture
def anthropic_messages_create_mock(monkeypatch):
    create_mock = mock.Mock()
    create_mock.return_value = anthropic.types.Message(
        id='asdf-1234',
        content=[
            anthropic.types.TextBlock(
                type='text',
                text='battlefield after the battle, littered with the bodies of the fallen',
            ),
        ],
        role='assistant',
        type='message',
        stop_reason='end_turn',
        model='claude-haiku-5-5',
        usage=anthropic.types.Usage(
            input_tokens=123,
            output_tokens=234,
        ),
    )
    monkeypatch.setattr('warriors.llms.anthropic.client.messages.create', create_mock)


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{'llm': LLM.CLAUDE}], indirect=True)
def test_resolve_battle(battle, anthropic_messages_create_mock):
    resolve_battle(None, battle.id, '1_2')
    game = battle.games.get(warrior_1=battle.warrior_1)
    assert game.text_unit.content == 'battlefield after the battle, littered with the bodies of the fallen'
    assert game.llm_version == 'claude-haiku-5-5'
    assert game.finish_reason == 'end_turn'


@pytest.mark.real_world
def test_resolve_battle_real_endpoint():
    text, stop_reason, llm_version = anthropic_resolve_battle('Test text', 'Another test text')
    assert isinstance(text, str)
    assert isinstance(stop_reason, str)
    assert isinstance(llm_version, str)
