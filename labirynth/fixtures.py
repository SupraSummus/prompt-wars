import pytest

from .factories import RoomFactory


@pytest.fixture
def room(request):
    return RoomFactory(
        **getattr(request, 'param', {}),
    )
