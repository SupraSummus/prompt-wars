import factory

from .models import Room


class RoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Room

    x = 0
    y = 0
    z = 0
