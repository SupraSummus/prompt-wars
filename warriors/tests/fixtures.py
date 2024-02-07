import pytest

from .factories import BattleFactory, WarriorFactory


@pytest.fixture
def warrior(request):
    return WarriorFactory(
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def battle(request, warrior):
    other_warrior = WarriorFactory()
    if warrior.id > other_warrior.id:
        warrior, other_warrior = other_warrior, warrior
    return BattleFactory(
        warrior_1=warrior,
        warrior_2=other_warrior,
        **getattr(request, 'param', {}),
    )
