from dataclasses import dataclass
from functools import lru_cache

import numpy
import numpy as np
from scipy.optimize import Bounds, minimize
from scipy.special import xlogy  # pylint: disable=no-name-in-module


# We have 2k playstyle parameters
# For k=0 this is standard Elo rating
default_k = 0


@dataclass(frozen=True)
class GameScore:
    score: float
    opponent_rating: float
    opponent_playstyle: list[float]


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
        method='L-BFGS-B',
        jac=lambda x: _gradient(x[0], x[1:], scores, k),
        options={
            'gtol': 1e-6,  # Gradient tolerance for convergence
        },
    )
    loss = result.fun
    return result.x[0], list(result.x[1:]), loss


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


def _gradient(
    rating: float,
    playstyle: list[float],
    scores: list[GameScore],
    k: int = default_k,
) -> np.ndarray:
    """
    Calculate the gradient of the loss function with respect to rating and playstyle parameters.
    Returns a numpy array with the gradient for [rating, playstyle[0], playstyle[1], ...]
    """
    # Convert inputs to numpy arrays
    playstyle = np.array(playstyle)
    real_scores = np.array([score.score for score in scores])
    n = len(scores)

    # Get predicted scores
    predicted_scores = get_expected_scores(rating, playstyle, scores, k)

    # Initialize gradient vector
    grad = np.zeros(1 + len(playstyle))

    # Get the omega matrix for playstyle interactions
    omega_matrix = compute_omega_matrix(k)

    # Constant factor in the sigmoid derivative
    log10_over_400 = np.log(10) / 400

    for i, score in enumerate(scores):
        y_pred = predicted_scores[i]
        y_real = real_scores[i]
        opponent_playstyle = np.array(score.opponent_playstyle)

        # This is the error term: (y_pred - y_real)
        error_term = y_pred - y_real

        # This is a common factor in our gradient: (y_pred - y_real) * log(10)/400 / n
        common_factor = error_term * log10_over_400 / n

        # Rating gradient: dL/dr = (y_pred - y_real) * log(10)/400 / n
        # Note: No negative sign here because:
        # - Increasing rating increases expected score
        # - If expected score > real score, we want to decrease rating
        grad[0] += common_factor

        # Playstyle gradient
        for j in range(len(playstyle)):
            # Calculate how this playstyle parameter interacts with opponent's playstyle
            # This is the row j of Ω multiplied by opponent playstyle vector
            playstyle_effect = np.sum(omega_matrix[j] * opponent_playstyle)

            # dL/dp_j = (y_pred - y_real) * log(10)/400 / n * playstyle_effect
            grad[j + 1] += common_factor * playstyle_effect

    return grad


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


def get_expected_game_score(
    own_rating: float,
    own_playstyle: list[float],
    opponent_rating: float,
    opponent_playstyle: list[float],
    k: int = default_k,
) -> float:
    """
    Calculate expected score for a game between two players.
    0 means we lose, 1 means we win.
    """
    own_playstyle = numpy.array(own_playstyle)
    assert own_playstyle.shape == (2 * k,)
    opponent_playstyle = numpy.array(opponent_playstyle)
    assert opponent_playstyle.shape == (2 * k,)

    playstyle_correction_matrix = compute_omega_matrix(k)
    playstyle_factor = own_playstyle @ playstyle_correction_matrix @ opponent_playstyle.T
    rating_delta = opponent_rating - own_rating - playstyle_factor
    return 1 / (1 + 10**(rating_delta / 400))


def binary_cross_entropy(real, predicted):
    assert len(real) == len(predicted)
    return -sum(xlogy(real, predicted) + xlogy(1 - real, 1 - predicted)) / len(real)


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
