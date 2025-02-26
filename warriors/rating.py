from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.optimize import Bounds, minimize
from scipy.special import xlogy  # pylint: disable=no-name-in-module


# We have 2k playstyle parameters
# For k=0 this is standard Elo rating
default_k = 0

# Pre-compute constant
LOG10_OVER_400 = np.log(10) / 400


@dataclass(frozen=True)
class GameScore:
    """Represents the outcome of a game and the opponent's parameters."""
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

    Returns:
        tuple: (rating, playstyle, loss)
    """
    if rating_guess is None:
        rating_guess = 0.0
    if playstyle_guess is None:
        playstyle_guess = np.zeros(2 * k)
    else:
        playstyle_guess = np.array(playstyle_guess)

    if allowed_rating_range == 0:
        return 0, [0] * (2 * k), 0

    allowed_playstyle_range = allowed_rating_range ** 0.5

    # Clip the initial guesses to the allowed ranges
    rating_guess = np.clip(rating_guess, -allowed_rating_range, allowed_rating_range)
    playstyle_guess = np.clip(playstyle_guess, -allowed_playstyle_range, allowed_playstyle_range)

    # Set up bounds for optimization
    lower_bounds = np.array([-allowed_rating_range] + [-allowed_playstyle_range] * (2 * k))
    upper_bounds = np.array([allowed_rating_range] + [allowed_playstyle_range] * (2 * k))
    bounds = Bounds(lb=lower_bounds, ub=upper_bounds)

    # Optimize
    result = minimize(
        lambda x: _loss(x[0], x[1:], scores, k),
        np.concatenate([[rating_guess], playstyle_guess]),
        bounds=bounds,
        method='L-BFGS-B',
        jac=lambda x: _gradient(x[0], x[1:], scores, k),
        options={'gtol': 1e-6},
    )

    return result.x[0], result.x[1:].tolist(), result.fun


def _loss(
    own_rating: float,
    own_playstyle: np.ndarray,
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
    playstyle: np.ndarray,
    scores: list[GameScore],
    k: int = default_k,
) -> np.ndarray:
    """
    Calculate the gradient of the loss function with respect to rating and playstyle parameters.
    Returns a numpy array with the gradient for [rating, playstyle[0], playstyle[1], ...]
    """
    if not isinstance(playstyle, np.ndarray):
        playstyle = np.array(playstyle)

    real_scores = np.array([score.score for score in scores])
    n = len(scores)

    # Get predicted scores
    predicted_scores = get_expected_scores(rating, playstyle, scores, k)

    # Calculate error terms
    errors = predicted_scores - real_scores

    # Common scaling factor
    common_factors = errors * LOG10_OVER_400 / n

    # Rating gradient is the sum of common factors
    rating_grad = np.sum(common_factors)

    # Get omega matrix for playstyle interactions
    omega_matrix = compute_omega_matrix(k)

    # Calculate playstyle gradients
    playstyle_grad = np.zeros_like(playstyle)

    for i, (common_factor, score) in enumerate(zip(common_factors, scores)):
        opponent_playstyle = np.array(score.opponent_playstyle)
        # Calculate how each playstyle parameter interacts with opponent's playstyle
        for j in range(len(playstyle)):
            playstyle_effect = np.sum(omega_matrix[j] * opponent_playstyle)
            playstyle_grad[j] += common_factor * playstyle_effect

    return np.concatenate([[rating_grad], playstyle_grad])


def get_expected_scores(
    own_rating: float,
    own_playstyle: np.ndarray,
    scores: list[GameScore],
    k: int = default_k,
) -> np.ndarray:
    """Calculate expected scores for multiple games."""
    if not isinstance(own_playstyle, np.ndarray):
        own_playstyle = np.array(own_playstyle)

    playstyle_correction_matrix = compute_omega_matrix(k)

    expected_scores = np.zeros(len(scores))
    for i, score in enumerate(scores):
        opponent_playstyle = np.array(score.opponent_playstyle)
        playstyle_factor = own_playstyle @ playstyle_correction_matrix @ opponent_playstyle
        rating_delta = score.opponent_rating - own_rating - playstyle_factor
        expected_scores[i] = 1 / (1 + 10**(rating_delta / 400))

    return expected_scores


def get_expected_game_score(
    own_rating: float,
    own_playstyle: np.ndarray,
    opponent_rating: float,
    opponent_playstyle: np.ndarray,
    k: int = default_k,
) -> float:
    """
    Calculate expected score for a game between two players.
    0 means we lose, 1 means we win.
    """
    if not isinstance(own_playstyle, np.ndarray):
        own_playstyle = np.array(own_playstyle)
    if not isinstance(opponent_playstyle, np.ndarray):
        opponent_playstyle = np.array(opponent_playstyle)

    playstyle_correction_matrix = compute_omega_matrix(k)
    playstyle_factor = own_playstyle @ playstyle_correction_matrix @ opponent_playstyle
    rating_delta = opponent_rating - own_rating - playstyle_factor
    return 1 / (1 + 10**(rating_delta / 400))


def binary_cross_entropy(real: np.ndarray, predicted: np.ndarray) -> float:
    """Calculate binary cross-entropy loss."""
    return -np.mean(xlogy(real, predicted) + xlogy(1 - real, 1 - predicted))


@lru_cache
def compute_omega_matrix(k: int) -> np.ndarray:
    """
    Compute the omega matrix for playstyle interactions.
    This matrix defines how playstyle parameters interact between players.
    """
    omega = np.zeros((2 * k, 2 * k))

    # For each playstyle dimension
    for i in range(1, k + 1):
        # Compute the indices for standard basis vectors
        idx_1 = 2 * i - 2  # adjust to 0-based indexing directly
        idx_2 = 2 * i - 1

        # Set the matrix elements directly
        omega[idx_1, idx_2] = 1
        omega[idx_2, idx_1] = -1

    return omega
