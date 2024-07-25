import uuid

from django.db import models
from django.db.models.expressions import CombinedExpression


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
