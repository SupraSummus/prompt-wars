import matplotlib.pyplot as plt
import numpy as np

from warriors.rating import get_expected_game_score


our_rating = 0
opponent_rating = 0

"""
2d plot of expected game score with given ooponent playstyle
"""

for n, our_playstyle in enumerate([
    (1, 1),
    (10, 10),
    (10, 0),
    (10, -10),
]):

    data = np.array(
        [
            [
                get_expected_game_score(
                    our_rating, our_playstyle,
                    opponent_rating, [i, j],
                    k=1,
                )
                for i in range(-20, 20)
            ]
            for j in range(-20, 20)
        ]
    )

    plt.subplot(2, 2, n + 1)
    plt.imshow(
        data,
        extent=(-20, 20, -20, 20),
        origin='lower',
        vmin=0.2,
        vmax=0.8,
    )
    plt.scatter(0, 0, color='red')
    plt.scatter(our_playstyle[0], our_playstyle[1], color='blue')
    plt.title(f'Our playstyle: {our_playstyle}')
    plt.colorbar(
        label='Expected game score',
    )

plt.tight_layout()
plt.savefig('expected_game_score.png')
