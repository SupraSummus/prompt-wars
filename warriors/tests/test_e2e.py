from unittest import mock

import pytest
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django_q.conf import Conf
from django_q.models import Schedule
from django_q.scheduler import scheduler
from freezegun import freeze_time

from ..exceptions import RateLimitError
from ..models import Battle, Warrior
from ..tasks import openai_client, resolve_battle


@pytest.mark.django_db(transaction=True)
def test_submit_warrior_e2e(client, mocked_recaptcha, monkeypatch, default_arena):
    monkeypatch.setattr(Conf, 'SYNC', True)

    moderation_result_mock = mock.MagicMock()
    moderation_result_mock.flagged = True
    moderation_mock = mock.MagicMock()
    moderation_mock.return_value.model = 'mderation-asdf'
    moderation_mock.return_value.results = [moderation_result_mock]
    monkeypatch.setattr(openai_client.moderations, 'create', moderation_mock)

    response = client.post(
        reverse('warrior_create'),
        data={
            'body': 'copy this to the output',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302, response.context['form'].errors
    path = response.url
    warrior_id = path.split('/')[-1]
    warrior = Warrior.objects.get(id=warrior_id)
    assert warrior.moderation_date is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('other_warrior', [
    {'body': 'copy this to the output'},
], indirect=True)
def test_battle_from_warriors_e2e(monkeypatch, warrior, other_warrior):
    monkeypatch.setattr(Conf, 'SYNC', True)
    assert warrior.rating == 0.0

    completion_mock = mock.MagicMock()
    completion_mock.message.content = 'Some result'
    completion_mock.finish_reason = 'stop'
    completions_mock = mock.MagicMock()
    completions_mock.choices = [completion_mock]
    completions_mock.model = 'gpt-3.5'
    completions_mock.system_fingerprint = '1234'
    create_mock = mock.Mock(return_value=completions_mock)
    monkeypatch.setattr(openai_client.chat.completions, 'create', create_mock)

    with transaction.atomic():
        battle = Battle.create_from_warriors(warrior, other_warrior)
        battle.refresh_from_db()
        assert battle.resolved_at_1_2 is None
        assert battle.resolved_at_2_1 is None

    battle.refresh_from_db()
    assert battle.rating_transferred_at is not None

    warrior.refresh_from_db()
    other_warrior.refresh_from_db()
    assert warrior.rating < 0
    assert other_warrior.rating > 0


@pytest.mark.django_db(transaction=True)
def test_battle_retry(battle, monkeypatch):
    monkeypatch.setattr(Conf, 'SYNC', True)

    monkeypatch.setattr(
        'warriors.tasks.resolve_battle_openai',
        mock.MagicMock(side_effect=RateLimitError),
    )
    assert not Schedule.objects.exists()
    resolve_battle(str(battle.id), '1_2')

    # battle still not resolved
    battle.refresh_from_db()
    assert battle.resolved_at_1_2 is None

    # we have a scheduled task for retrying the battle
    assert Schedule.objects.exists()

    # the task will be executed 10 minutes later
    monkeypatch.setattr(
        'warriors.tasks.resolve_battle_openai',
        mock.MagicMock(return_value=('Some result', 'stop', 'gpt-3.5/1234')),
    )
    now = timezone.now()
    with freeze_time(now + timezone.timedelta(minutes=10)):
        scheduler()

    # now battle is resolved
    battle.refresh_from_db()
    assert battle.resolved_at_1_2 is not None
