import pytest
from django.utils import timezone

from ..models import Battle, Warrior
from ..tasks import schedule_battles
from .factories import WarriorFactory


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
