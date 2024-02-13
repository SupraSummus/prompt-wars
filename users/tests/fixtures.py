import pytest

from .factories import UserFactory


@pytest.fixture
def user(request):
    return UserFactory(
        **getattr(request, 'param', {}),
    )
