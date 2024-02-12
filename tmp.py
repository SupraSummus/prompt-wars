from warriors.models import Warrior


total_changes = 0.0
n = 0
warriors = list(Warrior.objects.all())
for warrior in warriors:
    old_rating = warrior.rating
    warrior.update_rating(save=False)
    total_changes += abs(old_rating - warrior.rating)
    print(f'{warrior}: {old_rating} -> {warrior.rating}')
    n += 1
Warrior.objects.bulk_update(warriors, ['rating', 'games_played'])


print(f'Avg rating change: {total_changes / n}')
