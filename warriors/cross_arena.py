import logging

from .models import Arena, WarriorArena


logger = logging.getLogger(__name__)


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
