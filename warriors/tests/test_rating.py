import numpy as np
import pytest

from ..rating import GameScore, compute_omega_matrix, get_performance_rating


@pytest.fixture
def scores():
    return [
        GameScore(1, 1851, []),
        GameScore(0, 2457, []),
        GameScore(1, 1989, []),
        GameScore(1, 2379, []),
        GameScore(1, 2407, []),
    ]


def test_get_performance_rating(scores):
    rating, playstyle = get_performance_rating(
        scores,
        rating_guess=2000,
    )
    assert rating == pytest.approx(2550.5075)


def test_get_performance_rating_empty_range(scores):
    rating, playstyle = get_performance_rating(
        scores,
        allowed_rating_range=(42, 42),
    )
    assert rating == 42


@pytest.mark.parametrize("k", [0, 1, 3])
def test_omega_matrix_properties(k):
    omega = compute_omega_matrix(k)
    # Test matrix dimensions
    assert omega.shape == (2 * k, 2 * k), f"Expected shape (2*k, 2*k), but got {omega.shape}"
    # Test skew-symmetry
    assert np.allclose(omega, -omega.T), "Matrix is not skew-symmetric"
