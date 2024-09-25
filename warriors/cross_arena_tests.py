import pytest

from .cross_arena import find_and_unify_warrior
from .warriors import Warrior


@pytest.mark.django_db
@pytest.mark.parametrize('arena', [{'listed': True}], indirect=True)
def test_find_and_unify_warrior(warrior_arena, arena):
    find_and_unify_warrior()
    global_warrior = Warrior.objects.get(
        warrior_arenas=warrior_arena,
    )

    warrior_arena.refresh_from_db()
    assert warrior_arena.warrior == global_warrior

    assert warrior_arena.body == global_warrior.body
    assert warrior_arena.body_sha_256 == global_warrior.body_sha_256
