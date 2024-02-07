from unittest import mock

import pytest
from django.db import transaction
from django_q.conf import Conf

from ..models import Battle
from ..tasks import openai_client
from .factories import WarriorFactory


@pytest.mark.django_db(transaction=True)
def test_battle_from_warriors_e2e(monkeypatch, warrior):
    monkeypatch.setattr(Conf, 'SYNC', True)
    other_warrior = WarriorFactory(body='copy this to the output')
    assert warrior.rating == 0.0

    completion_mock = mock.MagicMock()
    completion_mock.message.content = 'Some result'
    completions_mock = mock.MagicMock()
    completions_mock.choices = [completion_mock]
    completions_mock.model = 'gpt-3.5'
    completions_mock.system_fingerprint = '1234'
    create_mock = mock.Mock(return_value=completions_mock)
    monkeypatch.setattr(openai_client.chat.completions, 'create', create_mock)

    with transaction.atomic():
        battle = Battle.from_warriors(warrior, other_warrior)
        battle.refresh_from_db()
        assert battle.resolved_at_1_2 is None
        assert battle.resolved_at_2_1 is None

    battle.refresh_from_db()
    assert battle.rating_transferred_at is not None

    warrior.refresh_from_db()
    other_warrior.refresh_from_db()
    assert warrior.rating < 0
    assert warrior.rating + other_warrior.rating == 0
