import random

import numpy as np
import pytest
from scipy.optimize import check_grad

from ..rating import (
    GameScore, _gradient, _loss, compute_omega_matrix, get_expected_game_score,
    get_performance_rating,
)


@pytest.fixture
def scores():
    return [
        GameScore(4 / 5, 1851, []),
        GameScore(4 / 5, 2457, []),
        GameScore(4 / 5, 1989, []),
        GameScore(4 / 5, 2379, []),
        GameScore(4 / 5, 2407, []),
    ]


def test_get_performance_rating(scores):
    rating, _, _ = get_performance_rating(scores)
    assert rating == pytest.approx(2550.5, abs=0.01)


def test_get_performance_rating_empty_range(scores):
    rating, playstyle, _ = get_performance_rating(
        scores,
        allowed_rating_range=0,
        k=3,
    )
    assert rating == 0
    assert playstyle == [0] * 6


@pytest.mark.parametrize("k", [0, 1, 3])
def test_omega_matrix_properties(k):
    omega = compute_omega_matrix(k)
    # Test matrix dimensions
    assert omega.shape == (2 * k, 2 * k), f"Expected shape (2*k, 2*k), but got {omega.shape}"
    # Test skew-symmetry
    assert np.allclose(omega, -omega.T), "Matrix is not skew-symmetric"


def test_rock_paper_scissors_scheme():
    """
    When we have three players that beat each other in a cycle,
    we should be able to predict match results using m-Elo k=1 system.
    """
    params = [
        (100, [10, 0]),
        (200, [0, 10]),
        (300, [5, 5]),
    ]

    # compute parameters
    for _ in range(100):
        new_params = []
        for i in range(3):
            prev_i = (i - 1) % 3
            next_i = (i + 1) % 3
            rating, playstyle, _ = get_performance_rating(
                [
                    GameScore(1, *params[prev_i]),
                    GameScore(0, *params[next_i]),
                ],
                rating_guess=params[i][0],
                playstyle_guess=params[i][1],
                k=1,
            )
            new_params.append((rating, playstyle))
        params = new_params

    # check predictions
    assert get_expected_game_score(*params[0], *params[1], k=1) == pytest.approx(0, abs=0.01)
    assert get_expected_game_score(*params[1], *params[2], k=1) == pytest.approx(0, abs=0.01)
    assert get_expected_game_score(*params[2], *params[0], k=1) == pytest.approx(0, abs=0.01)


def test_gradient():
    """Verify gradient calculation using scipy's check_grad"""
    k = 1
    # Create a small test case
    test_scores = [
        GameScore(0.75, 1200, [random.uniform(-10, 10) for _ in range(2 * k)]),
        GameScore(0.25, 800, [random.uniform(-10, 10) for _ in range(2 * k)])
    ]

    # Create test point
    test_point = [1000] + [random.uniform(-5, 5) for _ in range(2 * k)]

    # Function that returns just the loss
    def f(x):
        return _loss(x[0], x[1:], test_scores, k)

    # Function that returns just the gradient
    def g(x):
        return _gradient(x[0], x[1:], test_scores, k)

    # Check gradient
    error = check_grad(f, g, test_point)
    assert error < 1e-4
