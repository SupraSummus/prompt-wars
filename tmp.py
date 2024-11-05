from warriors.models import Battle


def do_some():
    qs = Battle.objects.filter(warrior_1=None) | Battle.objects.filter(warrior_2=None)
    qs = qs.select_related('warrior_arena_1', 'warrior_arena_2')
    battles = list(qs[:1000])
    for battle in battles:
        warrior_1_id = battle.warrior_arena_1.warrior_id
        warrior_2_id = battle.warrior_arena_2.warrior_id
        if warrior_1_id > warrior_2_id:
            warrior_1_id, warrior_2_id = warrior_2_id, warrior_1_id
        battle.warrior_1_id = warrior_1_id
        battle.warrior_2_id = warrior_2_id
    Battle.objects.bulk_update(battles, ['warrior_1_id', 'warrior_2_id'])
    return len(battles)


while True:
    n = do_some()
    if n == 0:
        break
    print('Updated', n)
