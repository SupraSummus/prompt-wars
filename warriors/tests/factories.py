import hashlib

import factory

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
    warrior_1 = factory.SubFactory(WarriorArenaFactory)
    warrior_2 = factory.SubFactory(WarriorArenaFactory)


class TextUnitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TextUnit

    content = factory.Sequence(lambda n: f'factory-made text unit body {n}')
    sha_256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.content.encode('utf-8')).digest()
    )
