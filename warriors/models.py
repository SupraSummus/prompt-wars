import datetime
import random
import uuid

from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .battles import LLM, Battle, ScoreAlgorithm
from .rating_models import RatingMixin
from .stats import ArenaStats
from .text_unit import TextUnit
from .warriors import Warrior


__all__ = ['ArenaStats', 'Warrior', 'TextUnit']


MATCHMAKING_MAX_RATING_DIFF = 100  # rating diff of 100 means expected score is 64%


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

    def create_battle(self, opponent, now=None):
        if now is None:
            now = timezone.now()

        battle = Battle.create_from_warriors(self, opponent)

        self.games_played = Battle.objects.with_warrior_arena(self).count()
        self.next_battle_schedule = now + self.get_next_battle_delay()
        self.save(update_fields=[
            'games_played',
            'next_battle_schedule',
        ])

        opponent.games_played = Battle.objects.with_warrior_arena(opponent).count()
        opponent.save(update_fields=['games_played'])

        # Generate voyage 3 embeddings in case not already generated.
        # Normally we generate them when warrior is created.
        # This is for old warriors created before we introduced embeddings.
        # Possibly this can be removed in the future.
        self.warrior.schedule_voyage_3_embedding()
        opponent.warrior.schedule_voyage_3_embedding()

        return battle

    def find_opponent(self, **kwargs):
        return self.find_opponents(**kwargs).order_by('?').select_for_update(
            no_key=True,
            skip_locked=True,
        ).first()

    def find_opponents(
        self,
        max_rating_diff=MATCHMAKING_MAX_RATING_DIFF,
    ):
        battle_worthy_qs = WarriorArena.objects.battleworthy()
        top_rating = self.rating + max_rating_diff
        bottom_rating = self.rating - max_rating_diff

        historic_battles = Battle.objects.with_warrior_arena(self).recent()

        return battle_worthy_qs.filter(
            arena_id=self.arena_id,
            rating__lt=top_rating,
            rating__gt=bottom_rating,
        ).exclude(
            id=self.id,
        ).exclude(
            warrior_id__in=historic_battles.values('warrior_1'),
        ).exclude(
            warrior_id__in=historic_battles.values('warrior_2'),
        )

    def get_next_battle_delay(self):
        """
        Get delay to the game N+1, where N is the number of games with this warrior.
        Games are exponentially less and less frequent.
        """
        K = 2
        time_unit = datetime.timedelta(minutes=1)
        exponent = self.games_played - random.random()
        if exponent > 25:
            # avoid overflow
            exponent = 25
        return max(
            K ** exponent - 1,
            0,
        ) * time_unit


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
