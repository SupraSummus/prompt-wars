from warriors.models import Battle
from warriors.text_unit import TextUnit


def do_some():
    battles = (
        Battle.objects.filter(text_unit_1_2__isnull=True) |
        Battle.objects.filter(text_unit_2_1__isnull=True)
    )[:100]
    battles = list(battles)
    for battle in battles:
        battle.text_unit_1_2 = TextUnit.get_or_create_by_content(
            battle.result_1_2,
            now=battle.resolved_at_1_2,
        )
        battle.text_unit_2_1 = TextUnit.get_or_create_by_content(
            battle.result_2_1,
            now=battle.resolved_at_2_1,
        )
    Battle.objects.bulk_update(
        battles,
        ['text_unit_1_2', 'text_unit_2_1'],
    )
    return len(battles)


while True:
    count = do_some()
    print(f'Updated {count} battles')
    if count == 0:
        break
