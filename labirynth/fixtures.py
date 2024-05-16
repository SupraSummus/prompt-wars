import pytest

from .factories import PlayerFactory, RoomFactory


@pytest.fixture
def player(request, user, room):
    return PlayerFactory(
        user=user,
        current_room=room,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def room(request):
    return RoomFactory(
        **getattr(request, 'param', {}),
    )
