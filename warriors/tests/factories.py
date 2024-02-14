import hashlib

import factory

from users.tests.factories import UserFactory

from ..models import Battle, Warrior, WarriorUserPermission


class WarriorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Warrior

    body = factory.Sequence(lambda n: f'factory-made warrior body {n}')
    body_sha_256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.body.encode('utf-8')).digest()
    )
    moderation_passed = True


class WarriorUserPermissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WarriorUserPermission

    warrior = factory.SubFactory(WarriorFactory)
    user = factory.SubFactory(UserFactory)


class BattleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Battle

    warrior_1 = factory.SubFactory(WarriorFactory)
    warrior_2 = factory.SubFactory(WarriorFactory)
