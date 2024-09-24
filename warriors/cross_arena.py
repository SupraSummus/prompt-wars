import logging

from .models import Arena, WarriorArena
from .warriors import Warrior


logger = logging.getLogger(__name__)


def find_and_unify_warrior():
    # find warrior-arena withut a warrior
    logger.info('Doing find_and_unify_warrior')
    warrior_arena = WarriorArena.objects.filter(
        warrior=None,
        arena__listed=True,
    ).order_by('id').first()
    if not warrior_arena:
        logger.info('No warrior-arena without warrior found')
        return
    warrior = get_or_create_warrior(warrior_arena)
    logger.info(f'Unified warrior-arena {warrior_arena.id} with warrior {warrior.id}')


def get_or_create_warrior(warrior_arena):
    warrior, created = Warrior.objects.get_or_create(
        body_sha_256=warrior_arena.body_sha_256,
        defaults={
            'body': warrior_arena.body,
        },
    )
    meld_warrior(warrior, warrior_arena)
    # ensure_warrior_on_all_arenas(warrior)
    return warrior


def ensure_warrior_on_all_arenas(warrior):
    for arena in Arena.objects.filter(listed=True):
        warrior_arena, created = WarriorArena.objects.get_or_create(
            arena=arena,
            body_sha_256=warrior.body_sha_256,
            defaults={
                'warrior': warrior,
                'body': warrior.body,
                'created_at': warrior.created_at,
                'created_by': warrior.created_by,
                'name': warrior.name,
                'author_name': warrior.author_name,
                'moderation_date': warrior.moderation_date,
                'moderation_passed': warrior.moderation_passed,
                'moderation_model': warrior.moderation_model,
                'public_battle_results': warrior.public_battle_results,
            },
        )
        if not created:
            meld_warrior(warrior, warrior_arena)


def meld_warrior(warrior, warrior_arena):
    assert warrior.body_sha_256 == warrior_arena.body_sha_256
    modified = False

    # assign authorship of the oldest instance
    if warrior_arena.created_at < warrior.created_at:
        warrior.created_at = warrior_arena.created_at
        warrior.created_by = warrior_arena.created_by
        warrior.name = warrior_arena.name
        warrior.author_name = warrior_arena.author_name
        modified = True

    # assign most recent moderation data
    if (
        # global warrior not moderated or
        (
            warrior_arena.moderation_passed and
            (warrior.moderation_passed is None)
        ) or
        # we have newer moderation data
        (
            warrior_arena.moderation_date and
            warrior.moderation_date and
            warrior_arena.moderation_date > warrior.moderation_date
        )
    ):
        warrior.moderation_date = warrior_arena.moderation_date
        warrior.moderation_passed = warrior_arena.moderation_passed
        warrior.moderation_model = warrior_arena.moderation_model
        modified = True

    # assign public_battle_results
    if (
        warrior_arena.public_battle_results and
        not warrior.public_battle_results
    ):
        warrior.public_battle_results = warrior_arena.public_battle_results
        modified = True

    if modified:
        warrior.save()

    # link warrior_arena to the warrior
    if warrior_arena.warrior != warrior:
        warrior_arena.warrior = warrior
        warrior_arena.save(update_fields=['warrior'])
