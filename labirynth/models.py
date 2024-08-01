import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.expressions import CombinedExpression
from django.utils import timezone


User = get_user_model()


class Room(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    # coordinates in hex grid. x + y + z = 0
    x = models.IntegerField()
    y = models.IntegerField()
    z = models.IntegerField()
    # "real world coordinates" are scaled by 2^zoom_level
    zoom_level = models.SmallIntegerField(
        default=0,
    )

    prompt = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['zoom_level', 'x', 'y', 'z'],
                name='unique_coords',
            ),
            models.CheckConstraint(
                check=CombinedExpression(
                    models.F('x') + models.F('y') + models.F('z'),
                    '=',
                    models.Value(0),
                    output_field=models.BooleanField(),
                ),
                name='hex_grid',
            ),
        ]


class RoomVersion(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    room = models.ForeignKey(
        to=Room,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    prompt = models.TextField()
    created_at = models.DateTimeField(
        default=timezone.now,
    )
    user = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
    )
    llm_version = models.CharField(
        max_length=100,
        blank=True,
    )

    class Meta:
        ordering = ['-created_at']
        get_latest_by = 'created_at'
