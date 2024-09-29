from warriors.models import WarriorUserPermission


def do_some():
    permissions = WarriorUserPermission.objects.filter(
        warrior=None,
    )
    i = 0
    for permission in permissions:
        alternative_permission = WarriorUserPermission.objects.get(
            user=permission.user,
            warrior=permission.warrior_arena.warrior,
        )
        alternative_permission.created_at = min(
            permission.created_at,
            alternative_permission.created_at,
        )
        alternative_permission.public_battle_results = (
            permission.public_battle_results or
            alternative_permission.public_battle_results
        )
        alternative_permission.name = max(
            permission.name,
            alternative_permission.name,
        )
        alternative_permission.save()
        permission.delete()
        i += 1
    return i


count = do_some()
print(f'Updated {count} permissions')
