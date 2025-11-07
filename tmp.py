from datetime import date, timedelta

from warriors.battles import Battle, DBGame


current_date = date(2020, 1, 1)

while True:
    next_date = current_date + timedelta(days=1)

    day_battles = list(Battle.objects.filter(scheduled_at__date=current_date))

    new_games = 0
    existing_games = 0

    for battle in day_battles:
        _, created = DBGame.objects.get_or_create(
            llm=battle.llm,
            warrior_1=battle.warrior_1,
            warrior_2=battle.warrior_2,
            scheduled_at=battle.scheduled_at,
            defaults={
                'input_sha256': battle.input_sha256_1_2,
                'text_unit': battle.text_unit_1_2,
                'finish_reason': battle.finish_reason_1_2,
                'llm_version': battle.llm_version_1_2,
                'resolved_at': battle.resolved_at_1_2,
                'attempts': battle.attempts_1_2,
            }
        )
        if created:
            new_games += 1
        else:
            existing_games += 1

        _, created = DBGame.objects.get_or_create(
            llm=battle.llm,
            warrior_1=battle.warrior_2,
            warrior_2=battle.warrior_1,
            scheduled_at=battle.scheduled_at,
            defaults={
                'input_sha256': battle.input_sha256_2_1,
                'text_unit': battle.text_unit_2_1,
                'finish_reason': battle.finish_reason_2_1,
                'llm_version': battle.llm_version_2_1,
                'resolved_at': battle.resolved_at_2_1,
                'attempts': battle.attempts_2_1,
            }
        )
        if created:
            new_games += 1
        else:
            existing_games += 1

    print(f"{current_date}: {new_games} new games, {existing_games} existing games (from {len(day_battles)} battles)")

    if day_battles:
        current_date = next_date

    else:
        next_battle = Battle.objects.filter(scheduled_at__date__gt=current_date).order_by('scheduled_at').first()
        if not next_battle:
            print(f"No more battles after {current_date}, stopping.")
            break
        current_date = next_battle.scheduled_at.date()

print("Done!")
