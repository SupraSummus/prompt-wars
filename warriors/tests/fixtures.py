import pytest

from .factories import (
    ArenaFactory, BattleFactory, WarriorArenaFactory,
    WarriorUserPermissionFactory,
)


@pytest.fixture
def arena(request):
    return ArenaFactory(
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def default_arena(arena, site, settings):
    arena.site = site
    arena.save(update_fields=['site'])
    settings.SITE_ID = site.id
    return arena


@pytest.fixture
def warrior_arena(request, arena):
    return WarriorArenaFactory(
        arena=arena,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def warrior_user_permission(request, warrior_arena, user):
    return WarriorUserPermissionFactory(
        warrior_arena=warrior_arena,
        user=user,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def other_warrior_arena(request, arena):
    return WarriorArenaFactory(
        arena=arena,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def battle(request, arena, warrior_arena, other_warrior_arena):
    if warrior_arena.id > other_warrior_arena.id:
        warrior_arena, other_warrior_arena = other_warrior_arena, warrior_arena
    return BattleFactory(
        arena=arena,
        warrior_1=warrior_arena,
        warrior_2=other_warrior_arena,
        **getattr(request, 'param', {}),
    )
