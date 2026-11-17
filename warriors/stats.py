import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .battles import Battle
from .rankings import Ranking
from .rating_models import WarriorRating


class RankingStats(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateTimeField(default=timezone.now, db_index=True)
    ranking = models.CharField(max_length=20, choices=Ranking.choices)

    warrior_count = models.PositiveIntegerField()
    battle_count = models.PositiveIntegerField()
    rating_quantiles = ArrayField(
        models.FloatField(),
        size=101,
        help_text=_('i-th element is the rating of the i-th percentile'),
    )

    class Meta:
        ordering = ['-date']

    @property
    def rating_quantile_labels(self):
        return rating_quantile_labels()


def rating_quantile_labels():
    return [i / 100 for i in range(101)]


def create_ranking_stats(now=None):
    if now is None:
        now = timezone.now()
    for ranking in Ranking:
        create_ranking_stats_for(ranking, now)


def create_ranking_stats_for(ranking, now):
    if RankingStats.objects.filter(ranking=ranking, date__date=now.date()).exists():
        return
    ratings = WarriorRating.objects.battleworthy().filter(ranking=ranking)
    rating_quantiles = ratings.aggregate(
        percentiles=PercentileDisc('rating', rating_quantile_labels())
    )['percentiles'] or []
    RankingStats.objects.create(
        ranking=ranking,
        date=now,
        warrior_count=ratings.count(),
        battle_count=Battle.objects.rated().count(),
        rating_quantiles=rating_quantiles,
    )


class PercentileDisc(models.Aggregate):
    function = 'percentile_disc'
    name = 'percentiles'
    template = '%(function)s(ARRAY %(percentiles)s) WITHIN GROUP (ORDER BY %(expressions)s)'

    def __init__(self, expression, percentiles, **extra):
        super().__init__(expression, output_field=ArrayField(models.FloatField()), **extra)
        self.extra['percentiles'] = percentiles
