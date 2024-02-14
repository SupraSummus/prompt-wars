import pytest

from .factories import (
    BattleFactory, WarriorFactory, WarriorUserPermissionFactory,
)


@pytest.fixture
def warrior(request):
    return WarriorFactory(
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def warrior_user_permission(request, warrior, user):
    return WarriorUserPermissionFactory(
        warrior=warrior,
        user=user,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def other_warrior(request):
    return WarriorFactory(
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def battle(request, warrior, other_warrior):
    if warrior.id > other_warrior.id:
        warrior, other_warrior = other_warrior, warrior
    return BattleFactory(
        warrior_1=warrior,
        warrior_2=other_warrior,
        **getattr(request, 'param', {}),
    )
