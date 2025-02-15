from django.db import transaction
from django_goals.models import schedule

from warriors.battles import Battle
from warriors.tasks import resolve_battle_1_2, resolve_battle_2_1


qs = Battle.objects.filter(
    arena_id='e61f750b-e909-4993-b4a1-d59ea383140c',
    finish_reason_1_2='',
)
for battle in qs[:5]:
    with transaction.atomic():
        print('1_2', battle.id)
        battle.resolved_at_1_2 = None
        battle.attempts_1_2 = 0
        battle.save(update_fields=['resolved_at_1_2', 'attempts_1_2'])
        schedule(resolve_battle_1_2, args=[str(battle.id)])


qs = Battle.objects.filter(
    arena_id='e61f750b-e909-4993-b4a1-d59ea383140c',
    finish_reason_2_1='',
)
for battle in qs[:5]:
    with transaction.atomic():
        print('2_1', battle.id)
        battle.resolved_at_2_1 = None
        battle.attempts_2_1 = 0
        battle.save(update_fields=['resolved_at_2_1', 'attempts_2_1'])
        schedule(resolve_battle_2_1, args=[str(battle.id)])
