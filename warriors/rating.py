"""
Functions to compute ideal performance rating for a given score in a tournament.
Based on wikipedia code: https://en.wikipedia.org/wiki/Performance_rating_(chess)#Calculation
"""


def get_expected_game_score(own_rating: float, opponent_rating: float) -> float:
    """
    Calculate expected score for a game between two players.
    """
    return 1 / (1 + 10**((opponent_rating - own_rating) / 400))


def get_expected_tournament_score(own_rating: float, opponent_ratings: list[float]) -> float:
    """
    Calculate expected score for a tournament with a list of opponents.
    """
    return sum(
        get_expected_game_score(own_rating, opponent_rating)
        for opponent_rating in opponent_ratings
    )


def get_performance_rating(
    score: float,
    opponent_ratings: list[float],
    precision: float = 0.001,
    allowed_rating_range: tuple[float, float] = (-4000, 4000),
) -> float:
    """
    Calculate mathematically perfect performance rating from a set of games.

    :param score: tournament score (sum of all game scores)
    :param opponent_ratings: list of opponent ratings in tournament games
    """

    # we use binary search
    lo, hi = allowed_rating_range

    while hi - lo > precision:
        mid = (lo + hi) / 2

        if get_expected_tournament_score(mid, opponent_ratings) < score:
            lo = mid
        else:
            hi = mid

    return mid
