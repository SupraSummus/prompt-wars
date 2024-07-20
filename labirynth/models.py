import uuid

from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.expressions import CombinedExpression
from django.utils import timezone


User = get_user_model()
EMBEDDING_DIM = 128


class Direction(models.IntegerChoices):
    UP = (0, 'up')
    UP_RIGHT = (1, 'up/right')
    DOWN_RIGHT = (2, 'down/right')
    DOWN = (3, 'down')
    DOWN_LEFT = (4, 'down/left')
    UP_LEFT = (5, 'up/left')


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
    zoom_level = models.PositiveSmallIntegerField(
        default=0,
    )

    prompt = models.TextField()

    authored_at = models.DateTimeField(null=True)
    authored_by = models.ForeignKey(to=User, on_delete=models.PROTECT, null=True)

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


class Player(models.Model):
    user = models.OneToOneField(
        to=User,
        on_delete=models.CASCADE,
        primary_key=True,
    )
    current_room = models.ForeignKey(
        to=Room,
        on_delete=models.SET_NULL,
        null=True,
    )


class SpellCastState(models.TextChoices):
    # waiting for the system to finish the llm call
    ECHOING = 'echoing'
    # waiting for the system to finish the embedding and determine direction
    EMBEDDING = 'embedding'
    # oops, something went wrong
    ERROR = 'error'
    # all done
    EXITED = 'done'


class SpellCast(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    player = models.ForeignKey(
        to=Player,
        on_delete=models.PROTECT,
    )
    room = models.ForeignKey(
        to=Room,
        on_delete=models.PROTECT,
    )
    state = models.CharField(
        max_length=10,
        choices=SpellCastState.choices,
    )
    spell = models.TextField()
    spell_at = models.DateTimeField(default=timezone.now)
    echo = models.TextField()
    embedding = ArrayField(
        size=EMBEDDING_DIM,
        base_field=models.FloatField(),
    )
    direction = models.IntegerField(choices=Direction.choices)
