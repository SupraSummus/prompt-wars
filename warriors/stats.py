import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


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


def create_arena_stats():
    from .models import Arena
    now = timezone.now()
    for arena in Arena.objects.all():
        create_arena_stats_for_arena(arena, now)


def create_arena_stats_for_arena(arena, now):
    from .models import Battle, Warrior
    if ArenaStats.objects.filter(arena=arena, date__date=now.date()).exists():
        return
    warriors_qs = Warrior.objects.filter(arena=arena, moderation_passed=True)
    warrior_count = warriors_qs.count()
    battle_count = Battle.objects.filter(arena=arena).count()
    rating_quantiles = warriors_qs.aggregate(
        percentiles=PercentileDisc('rating', [i / 100 for i in range(101)]),
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
