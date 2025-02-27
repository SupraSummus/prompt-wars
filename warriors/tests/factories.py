import hashlib

import factory
from django.utils import timezone

from users.tests.factories import UserFactory

from ..models import LLM, Arena, Battle, WarriorArena, WarriorUserPermission
from ..text_unit import TextUnit
from ..warriors import Warrior


class ArenaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Arena

    name = factory.Sequence(lambda n: f'factory-made arena {n}')
    llm = LLM.OPENAI_GPT


class WarriorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Warrior

    body = factory.Sequence(lambda n: f'factory-made warrior body {n}')
    body_sha_256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.body.encode('utf-8')).digest()
    )
    moderation_passed = True


class WarriorArenaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WarriorArena

    arena = factory.SubFactory(ArenaFactory)
    warrior = factory.SubFactory(WarriorFactory)


class WarriorUserPermissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WarriorUserPermission

    warrior = factory.SubFactory(WarriorFactory)
    user = factory.SubFactory(UserFactory)


class BattleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Battle

    arena = factory.SubFactory(ArenaFactory)
    warrior_1 = factory.SubFactory(WarriorFactory)
    warrior_2 = factory.SubFactory(WarriorFactory)


def batch_create_battles(arena, warrior_arena, n):
    """Create n battles between warrior_arena and new opponents in the same arena."""
    for _ in range(n):
        other_warrior_arena = WarriorArenaFactory(arena=arena)
        battle_warrior_1 = warrior_arena.warrior
        battle_warrior_2 = other_warrior_arena.warrior
        if battle_warrior_1.id > battle_warrior_2.id:
            battle_warrior_1, battle_warrior_2 = battle_warrior_2, battle_warrior_1
        BattleFactory(
            arena=arena,
            llm=arena.llm,
            warrior_1=battle_warrior_1,
            warrior_2=battle_warrior_2,
            resolved_at_1_2=timezone.now(),
            text_unit_1_2=TextUnitFactory(),
            resolved_at_2_1=timezone.now(),
            text_unit_2_1=TextUnitFactory(),
        )


class TextUnitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TextUnit

    content = factory.Sequence(lambda n: f'factory-made text unit body {n}')
    sha_256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.content.encode('utf-8')).digest()
    )
