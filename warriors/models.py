import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .rating_models import WarriorRating
from .score import GameScore
from .stats import RankingStats
from .text_unit import TextUnit
from .warriors import Warrior


__all__ = [
    'RankingStats', 'Warrior', 'WarriorRating', 'TextUnit',
    'GameScore',
]


class LegacyWarriorArena(models.Model):
    """
    An id a `warrior-arena/<id>/` URL carries, and the warrior it names.

    Those URLs are linked from outside the site and held in sessions,
    so each keeps leading to its warrior's page (`legacy_warrior_arena` in `views.py`).
    """
    id = models.UUIDField(
        primary_key=True,
        editable=False,
    )
    warrior = models.ForeignKey(
        to=Warrior,
        on_delete=models.CASCADE,
        related_name='+',
    )


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
