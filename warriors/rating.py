from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, minimize


"""
Functions to compute ideal performance rating for a given score in a tournament.
Based on wikipedia code: https://en.wikipedia.org/wiki/Performance_rating_(chess)#Calculation
"""


# We have 2k playstyle parameters
# For k=0 this is standard Elo rating
k = 0


def get_expected_game_score(
    own_rating: float,
    own_playstyle: list[float],
    opponent_rating: float,
    opponent_playstyle: list[float],
) -> float:
    """
    Calculate expected score for a game between two players.
    """
    return 1 / (1 + 10**((opponent_rating - own_rating) / 400))


@dataclass(frozen=True)
class GameScore:
    score: float
    opponent_rating: float
    opponent_playstyle: list[float]


def get_torunament_loss(
    own_rating: float,
    own_playstyle: list[float],
    scores: list[GameScore],
) -> float:
    """
    Compute loss for estimation of scores in a tournament.
    """
    return sum(get_tournament_residuals(own_rating, own_playstyle, scores)) ** 2


def get_tournament_residuals(
    own_rating: float,
    own_playstyle: list[float],
    scores: list[GameScore],
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
        )
        residuals.append(score.score - expected_score)
    return residuals


def get_performance_rating(
    scores: list[GameScore],
    rating_guess: float = None,  # initial guess
    playstyle_guess: list[float] = None,  # initial guess
    allowed_rating_range: tuple[float, float] = (-4000, 4000),
) -> tuple[float, list[float]]:
    """
    Calculate performance rating from a set of games.
    """
    if rating_guess is None:
        rating_guess = 0.0
    if playstyle_guess is None:
        playstyle_guess = [0.0] * (2 * k)
    result = minimize(
        lambda x: get_torunament_loss(x[0], x[1:], scores),
        [rating_guess] + playstyle_guess,
        bounds=Bounds(
            lb=[allowed_rating_range[0]] + [-1000] * (2 * k),
            ub=[allowed_rating_range[1]] + [1000] * (2 * k),
        ),
        tol=1e-8,
    )
    return result.x[0], list(result.x[1:])


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


# called also "Omega matrix"
playstyle_correction_matrix = compute_omega_matrix(k)
