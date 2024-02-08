from unittest import mock

import pytest
from django.utils import timezone

from ..models import Battle, Warrior
from ..tasks import (
    do_moderation, openai_client, schedule_battles, transfer_rating,
)
from .factories import WarriorFactory


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'name': 'Test Warrior',
    'author': 'Test Author',
}], indirect=True)
@pytest.mark.parametrize('moderation_flagged', [True, False])
def test_do_moderation(warrior, monkeypatch, moderation_flagged):
    assert warrior.body
    assert warrior.name
    assert warrior.author

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
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'resolved_at_2_1': timezone.now(),
}], indirect=True)
def test_transfer_rating(battle):
    transfer_rating(battle.id)
    battle.refresh_from_db()
    assert battle.rating_transferred_at is not None
    assert battle.warrior_1_rating is not None
    assert battle.warrior_2_rating is not None
    assert battle.warrior_1.next_battle_schedule is not None
    assert battle.warrior_2.next_battle_schedule is not None
