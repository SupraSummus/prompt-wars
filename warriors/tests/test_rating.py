import pytest

from ..rating import get_performance_rating


def test_get_performance_rating():
    assert get_performance_rating(
        4,
        [1851, 2457, 1989, 2379, 2407],
    ) == pytest.approx(2550.5075)
