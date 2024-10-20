from warriors.models import WarriorArena


for warrior_arena in WarriorArena.objects.battleworthy().filter(
    warrior__voyage_3_embedding=[],
    warrior__voyage_3_embedding_goal=None,
).order_by('-rating')[:10]:
    print(warrior_arena.id, warrior_arena.name)
    warrior_arena.warrior.schedule_voyage_3_embedding()
