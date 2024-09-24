import pytest

from .cross_arena import find_and_unify_warrior
from .warriors import Warrior


@pytest.mark.django_db
@pytest.mark.parametrize('arena', [{'listed': True}], indirect=True)
def test_find_and_unify_warrior(warrior, arena):
    find_and_unify_warrior()
    global_warrior = Warrior.objects.get(
        warrior_arenas=warrior,
    )

    warrior.refresh_from_db()
    assert warrior.warrior == global_warrior

    assert warrior.body == global_warrior.body
    assert warrior.body_sha_256 == global_warrior.body_sha_256
