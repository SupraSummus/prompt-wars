from dataclasses import dataclass
from functools import lru_cache

import numpy
import numpy as np
from scipy.optimize import Bounds, least_squares


# We have 2k playstyle parameters
# For k=0 this is standard Elo rating
default_k = 0


def get_expected_game_score(
    own_rating: float,
    own_playstyle: list[float],
    opponent_rating: float,
    opponent_playstyle: list[float],
    k: int = default_k,
) -> float:
    """
    Calculate expected score for a game between two players.
    """
    own_playstyle = numpy.array(own_playstyle)
    assert own_playstyle.shape == (2 * k,)
    opponent_playstyle = numpy.array(opponent_playstyle)
    assert opponent_playstyle.shape == (2 * k,)

    playstyle_correction_matrix = compute_omega_matrix(k)
    playstyle_factor = own_playstyle @ playstyle_correction_matrix @ opponent_playstyle.T
    rating_delta = opponent_rating - own_rating - playstyle_factor
    return 1 / (1 + 10**(rating_delta / 400))


@dataclass(frozen=True)
class GameScore:
    score: float
    opponent_rating: float
    opponent_playstyle: list[float]


def get_tournament_residuals(
    own_rating: float,
    own_playstyle: list[float],
    scores: list[GameScore],
    k: int = default_k,
) -> float:
    """
    Given player rating and tournament scores compute residuals.
    (Residuals are differences between expected and actual scores)
    """
    residuals = []
    for score in scores:
        expected_score = get_expected_game_score(
            own_rating, own_playstyle,
            score.opponent_rating, score.opponent_playstyle,
            k,
        )
        residuals.append(score.score - expected_score)
    return residuals


def get_performance_rating(
    scores: list[GameScore],
    rating_guess: float = None,  # initial guess
    playstyle_guess: list[float] = None,  # initial guess
    allowed_rating_range: float = 4000,
    k: int = default_k,
) -> tuple[float, list[float], float]:
    """
    Calculate performance rating from a set of games.
    """
    if rating_guess is None:
        rating_guess = 0.0
    if playstyle_guess is None:
        playstyle_guess = [0.0] * (2 * k)
    if allowed_rating_range == 0:
        return 0, [0] * (2 * k), 0
    allowed_playstyle_range = allowed_rating_range ** 0.5
    result = least_squares(
        lambda x: get_tournament_residuals(x[0], x[1:], scores, k),
        [rating_guess] + playstyle_guess,
        bounds=Bounds(
            lb=[-allowed_rating_range] + [-allowed_playstyle_range] * (2 * k),
            ub=[allowed_rating_range] + [allowed_playstyle_range] * (2 * k),
        ),
    )
    loss = sum(residual**2 for residual in result.fun) / len(result.fun)
    return result.x[0], list(result.x[1:]), loss


@lru_cache
def compute_omega_matrix(k):
    # Initialize the Omega matrix with zeros
    omega = np.zeros((2 * k, 2 * k))

    # Iterate over the range of k
    for i in range(1, k + 1):
        # Compute the indices for standard basis vectors
        idx_1 = 2 * i - 1
        idx_2 = 2 * i

        # Create the standard basis vectors
        e_1 = np.zeros(2 * k)
        e_2 = np.zeros(2 * k)
        e_1[idx_1 - 1] = 1
        e_2[idx_2 - 1] = 1

        # Compute the outer products
        outer_prod_1 = np.outer(e_1, e_2)
        outer_prod_2 = np.outer(e_2, e_1)

        # Compute the difference of outer products
        diff_matrix = outer_prod_1 - outer_prod_2

        # Add the difference matrix to Omega
        omega += diff_matrix

    return omega
