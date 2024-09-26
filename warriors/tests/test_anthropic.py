from unittest import mock

import anthropic
import pytest

from ..models import LLM
from ..tasks import resolve_battle


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
        model='claude-3-haiku-20240307',
        usage=anthropic.types.Usage(
            input_tokens=123,
            output_tokens=234,
        ),
    )
    monkeypatch.setattr('warriors.anthropic.client.messages.create', create_mock)


@pytest.mark.django_db
@pytest.mark.parametrize('arena', [{'llm': LLM.CLAUDE_3_HAIKU}], indirect=True)
def test_resolve_battle(battle, anthropic_messages_create_mock):
    resolve_battle(battle.id, '1_2')
    battle.refresh_from_db()
    assert battle.text_unit_1_2.content == 'battlefield after the battle, littered with the bodies of the fallen'
    assert battle.llm_version_1_2 == 'claude-3-haiku-20240307'
    assert battle.finish_reason_1_2 == 'end_turn'
