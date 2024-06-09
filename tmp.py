import matplotlib.pyplot as plt

from warriors.models import Warrior


warriors = Warrior.objects.filter(
    arena_id='406b3ac1-39c4-4579-a6ed-35463bfecfd1',
    moderation_passed=True,
).order_by('-rating')[:100]


# scatter plot of rating_playstyle 2d vetors
plt.figure(figsize=(10, 10))
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
plt.title('Warriors playstyle')
plt.savefig('playstyle.png')
