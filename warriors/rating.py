from dataclasses import dataclass
from functools import lru_cache

import numpy
import numpy as np
from scipy.optimize import Bounds, minimize
from scipy.special import xlogy  # pylint: disable=no-name-in-module


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


def _loss(
    own_rating: float,
    own_playstyle: list[float],
    scores: list[GameScore],
    k: int = default_k,
) -> float:
    """
    Calculate the loss function for score predictions using params vs real scores.
    """
    real_scores = np.array([score.score for score in scores])
    predicted_scores = get_expected_scores(own_rating, own_playstyle, scores, k)
    return binary_cross_entropy(real_scores, predicted_scores)


def get_expected_scores(
    own_rating: float,
    own_playstyle: list[float],
    scores: list[GameScore],
    k: int = default_k,
) -> float:
    expected_scores = []
    for score in scores:
        expected_score = get_expected_game_score(
            own_rating, own_playstyle,
            score.opponent_rating, score.opponent_playstyle,
            k,
        )
        expected_scores.append(expected_score)
    return np.array(expected_scores)


def binary_cross_entropy(real, predicted):
    assert len(real) == len(predicted)
    return -sum(xlogy(real, predicted) + xlogy(1 - real, 1 - predicted)) / len(real)


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

    # clip the initial guess to the allowed range
    rating_guess = max(-allowed_rating_range, min(allowed_rating_range, rating_guess))
    playstyle_guess = [
        max(-allowed_playstyle_range, min(allowed_playstyle_range, x))
        for x in playstyle_guess
    ]

    result = minimize(
        lambda x: _loss(x[0], x[1:], scores, k),
        [rating_guess] + playstyle_guess,
        bounds=Bounds(
            lb=[-allowed_rating_range] + [-allowed_playstyle_range] * (2 * k),
            ub=[allowed_rating_range] + [allowed_playstyle_range] * (2 * k),
        ),
    )
    loss = result.fun
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
