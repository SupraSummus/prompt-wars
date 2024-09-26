from warriors.models import WarriorUserPermission


def do_some():
    permissions = WarriorUserPermission.objects.filter(
        warrior=None,
    )[:200]
    permissions = list(permissions)
    i = 0
    for permission in permissions:
        permission.warrior = permission.warrior_arena.warrior
        try:
            permission.save(update_fields=['warrior'])
        except Exception as e:
            print(f'Error updating permission {permission.pk}: {e}')
        else:
            i += 1
    return i


while True:
    count = do_some()
    print(f'Updated {count} permissions')
    if count == 0:
        break
