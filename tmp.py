from warriors.battles import Battle
from warriors.tasks import resolve_battle


qs = Battle.objects.filter(
    arena_id='e61f750b-e909-4993-b4a1-d59ea383140c',
    finish_reason_1_2='',
)
for battle in qs[:1]:
    print(battle.id)
    battle.resolved_at_1_2 = None
    battle.save(update_fields=['resolved_at_1_2'])
    resolve_battle(battle.id, '1_2')
