from warriors.models import Battle


for battle in Battle.objects.filter(
    scheduled_at__gte='2024-10-31T21:04:57.175374+00:00',
    scheduled_at__lte='2024-11-08T22:23:21.981115+00:00',
):
    print(battle.id)
    battle.lcs_len_1_2_2, battle.lcs_len_2_1_1 = battle.lcs_len_2_1_1, battle.lcs_len_1_2_2
    battle.save(update_fields=['lcs_len_1_2_2', 'lcs_len_2_1_1'])
