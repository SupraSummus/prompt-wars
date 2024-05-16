import factory

from .models import Player, Room


class RoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Room

    x = 0
    y = 0
    z = 0


class PlayerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Player
