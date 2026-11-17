import pytest

from .rankings import Ranking
from .stats import RankingStats, create_ranking_stats
from .tests.factories import WarriorRatingFactory


@pytest.mark.django_db
def test_create_ranking_stats_empty():
    create_ranking_stats()
    assert {
        (stats.ranking, stats.warrior_count, stats.battle_count)
        for stats in RankingStats.objects.all()
    } == {(ranking.value, 0, 0) for ranking in Ranking}


@pytest.mark.django_db
def test_create_ranking_stats():
    for rating in range(10):
        WarriorRatingFactory.create(ranking=Ranking.SEMANTIC, rating=rating)
    create_ranking_stats()
    stats = RankingStats.objects.get(ranking=Ranking.SEMANTIC)
    assert stats.warrior_count == 10
    assert stats.battle_count == 0
    assert len(stats.rating_quantiles) == 101
    assert stats.rating_quantiles[0] == 0
    assert stats.rating_quantiles[100] == 9
    # the same warriors stand in the other ranking, unrated there
    stats = RankingStats.objects.get(ranking=Ranking.LCS)
    assert stats.warrior_count == 10
    assert stats.rating_quantiles[100] == 0
