import factory

from ..models import Warrior


class WarriorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Warrior

    body = factory.Sequence(lambda n: f'factory-made warrior body {n}')
