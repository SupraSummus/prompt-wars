import hashlib
import uuid

from django.db import models
from django.utils import timezone


class TextUnit(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    content = models.TextField()
    sha_256 = models.BinaryField(
        max_length=32,
        unique=True,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(
                check=models.Q(sha_256=models.Func(
                    models.Func(
                        models.F('content'),
                        models.Value('utf-8'),
                        function='convert_to',
                    ),
                    function='sha256',
                )),
                name='text_unit_sha_256',
            ),
        ]

    @classmethod
    def get_or_create_by_content(cls, content, now=None):
        if now is None:
            now = timezone.now()
        sha_256 = hashlib.sha256(content.encode('utf-8')).digest()
        text_unit, created = cls.objects.get_or_create(
            sha_256=sha_256,
            defaults={
                'content': content,
                'created_at': now,
            },
        )
        cls.objects.filter(pk=text_unit.pk).update(
            created_at=models.functions.Least('created_at', now),
        )
        return text_unit
