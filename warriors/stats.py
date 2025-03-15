import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .battles import Battle


class ArenaStats(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateTimeField(default=timezone.now, db_index=True)
    arena = models.ForeignKey(to='Arena', on_delete=models.CASCADE)

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


def create_arena_stats(now=None):
    from .models import Arena
    if now is None:
        now = timezone.now()
    for arena in Arena.objects.all():
        create_arena_stats_for_arena(arena, now)


def create_arena_stats_for_arena(arena, now):
    if ArenaStats.objects.filter(arena=arena, date__date=now.date()).exists():
        return
    warriors_qs = arena.warriors.battleworthy()
    warrior_count = warriors_qs.count()
    battle_count = Battle.objects.filter(
        llm=arena.llm,
    ).count()
    rating_quantiles = warriors_qs.aggregate(
        percentiles=PercentileDisc('rating', rating_quantile_labels())
    )['percentiles'] or []
    ArenaStats.objects.create(
        arena=arena,
        date=now,
        warrior_count=warrior_count,
        battle_count=battle_count,
        rating_quantiles=rating_quantiles,
    )


class PercentileDisc(models.Aggregate):
    function = 'percentile_disc'
    name = 'percentiles'
    template = '%(function)s(ARRAY %(percentiles)s) WITHIN GROUP (ORDER BY %(expressions)s)'

    def __init__(self, expression, percentiles, **extra):
        super().__init__(expression, output_field=ArrayField(models.FloatField()), **extra)
        self.extra['percentiles'] = percentiles
