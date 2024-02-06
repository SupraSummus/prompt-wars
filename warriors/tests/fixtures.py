import pytest

from .factories import WarriorFactory


@pytest.fixture
def warrior(request):
    return WarriorFactory(
        **getattr(request, 'param', {}),
    )
