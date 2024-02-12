from warriors.lcs import lcs_len
from warriors.models import Battle


def update_lcs_len(game):
    if not game.resolved_at:
        return
    game.lcs_len_1 = lcs_len(game.warrior_1.body, game.result)
    game.lcs_len_2 = lcs_len(game.warrior_2.body, game.result)
    game.save(update_fields=['lcs_len_1', 'lcs_len_2'])


for battle in Battle.objects.all():
    update_lcs_len(battle.game_1_2)
    update_lcs_len(battle.game_2_1)
