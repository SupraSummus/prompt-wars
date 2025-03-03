import uuid

from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .battles import LLM
from .rating_models import RatingMixin
from .score import GameScore, ScoreAlgorithm
from .stats import ArenaStats
from .text_unit import TextUnit
from .warriors import Warrior


__all__ = [
    'ArenaStats', 'Warrior', 'TextUnit',
    'GameScore',
]


class Arena(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    site = models.OneToOneField(
        to=Site,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    name = models.CharField(
        max_length=40,
        unique=True,
    )
    listed = models.BooleanField(
        default=False,
    )
    enabled = models.BooleanField(
        default=True,
    )
    llm = models.CharField(
        max_length=20,
        choices=LLM.choices,
    )
    score_algorithm = models.CharField(
        max_length=20,
        choices=ScoreAlgorithm.choices,
        default=ScoreAlgorithm.LCS,
    )
    description = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class WarriorArenaQuerySet(models.QuerySet):
    def battleworthy(self):
        return self.filter(
            warrior__moderation_passed=True,
        )


class WarriorArena(RatingMixin, models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    warrior = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='warrior_arenas',
    )
    arena = models.ForeignKey(
        to=Arena,
        on_delete=models.CASCADE,
        related_name='warriors',
    )

    @property
    def body(self):
        return self.warrior.body

    @property
    def body_sha_256(self):
        return self.warrior.body_sha_256

    @property
    def created_at(self):
        return self.warrior.created_at

    @property
    def created_by(self):
        return self.warrior.created_by

    @property
    def name(self):
        return self.warrior.name

    @property
    def author_name(self):
        return self.warrior.author_name

    games_played = models.PositiveIntegerField(
        default=0,
    )

    @property
    def moderation_date(self):
        return self.warrior.moderation_date

    @property
    def moderation_passed(self):
        return self.warrior.moderation_passed

    @property
    def moderation_model(self):
        return self.warrior.moderation_model

    @property
    def public_battle_results(self):
        return self.warrior.public_battle_results

    next_battle_schedule = models.DateTimeField(
        default=timezone.now,
    )

    @property
    def rating_error_abs(self):
        return abs(self.rating_error)

    objects = WarriorArenaQuerySet.as_manager()

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=['arena', 'warrior'],
                name='arena_warrior_unique',
            ),
        ]
        indexes = [
            *RatingMixin.Meta.indexes,
            models.Index(
                fields=['next_battle_schedule'],
                name='next_battle_schedule_index',
                condition=models.Q(moderation_passed=True),
            ),
        ]

    def __str__(self):
        if self.moderation_passed is not True:
            return str(self.id)
        return self.name or str(self.id)

    def get_absolute_url(self):
        return reverse('warrior_detail', args=[str(self.id)])


def get_or_create_warrior_arenas(arena, warrior_ids):
    """Get WarriorArena objects for given warrior_ids in given arena.
    Returns dict warrior_id -> WarriorArena.
    """
    warrior_ids = set(warrior_ids)
    warrior_arenas = {
        w.warrior_id: w
        for w in WarriorArena.objects.filter(
            arena=arena,
            warrior_id__in=warrior_ids,
        )
    }
    missing_warrior_arenas = warrior_ids - set(warrior_arenas.keys())
    WarriorArena.objects.bulk_create([
        WarriorArena(
            arena=arena,
            warrior_id=warrior_id,
        )
        for warrior_id in missing_warrior_arenas
    ])
    warrior_arenas.update({
        w.warrior_id: w
        for w in WarriorArena.objects.filter(
            arena=arena,
            warrior_id__in=missing_warrior_arenas,
        )
    })
    return warrior_arenas


class WarriorUserPermission(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    warrior = models.ForeignKey(
        to=Warrior,
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )
    name = models.CharField(
        max_length=40,
        blank=True,
    )
    public_battle_results = models.BooleanField(
        default=False,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['warrior', 'user'],
                name='warrior_user_unique',
            ),
        ]
