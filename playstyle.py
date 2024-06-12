import matplotlib.pyplot as plt
from django.utils import timezone

from warriors.models import Warrior


def do_scatter(arena_id, filename):
    warriors = Warrior.objects.filter(
        arena_id=arena_id,
        moderation_passed=True,
    ).order_by('-rating')[:100]

    # scatter plot of rating_playstyle 2d vetors
    plt.figure(figsize=(30, 30))
    for warrior in warriors:
        if not warrior.rating_playstyle:
            print('skip', warrior.id)
            continue
        plt.scatter(
            warrior.rating_playstyle[0],
            warrior.rating_playstyle[1],
        )
        plt.annotate(
            warrior.name,
            (warrior.rating_playstyle[0], warrior.rating_playstyle[1]),
        )

    plt.xlabel('Playstyle 1')
    plt.ylabel('Playstyle 2')
    now = timezone.now()
    plt.title('Warriors playstyle ' + now.strftime('%Y-%m-%d %H:%M:%S %Z'))
    plt.savefig(filename)


do_scatter('12b383b6-06a0-408e-bcec-3879818cc87a', 'playstyle_haiku.png')
do_scatter('406b3ac1-39c4-4579-a6ed-35463bfecfd1', 'playstyle_gpt.png')
