from warriors.models import Battle
from warriors.text_unit import TextUnit


def do_some():
    battles_1_2 = Battle.objects.filter(
        text_unit_1_2__isnull=True,
        resolved_at_1_2__isnull=False,
    )[:50]
    battles_1_2 = list(battles_1_2)
    for battle in battles_1_2:
        battle.text_unit_1_2 = TextUnit.get_or_create_by_content(
            battle.result_1_2,
            now=battle.resolved_at_1_2,
        )
    Battle.objects.bulk_update(
        battles_1_2,
        ['text_unit_1_2'],
    )

    battles_2_1 = Battle.objects.filter(
        text_unit_2_1__isnull=True,
        resolved_at_2_1__isnull=False,
    )[:50]
    battles_2_1 = list(battles_2_1)
    for battle in battles_2_1:
        battle.text_unit_2_1 = TextUnit.get_or_create_by_content(
            battle.result_2_1,
            now=battle.resolved_at_2_1,
        )
    Battle.objects.bulk_update(
        battles_2_1,
        ['text_unit_2_1'],
    )

    return len(battles_1_2) + len(battles_2_1)


while True:
    count = do_some()
    print(f'Updated {count} battles')
    if count == 0:
        break
