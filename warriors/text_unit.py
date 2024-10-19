import hashlib
import uuid

import voyageai
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django_goals.models import AllDone, Goal, RetryMeLater, schedule


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
    voyage_3_embedding = ArrayField(
        models.FloatField(),
        size=1024,
        default=list,
    )
    voyage_3_embedding_goal = models.OneToOneField(
        to=Goal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def schedule_voyage_3_embedding(self):
        if (
            self.voyage_3_embedding or
            self.voyage_3_embedding_goal
        ):
            return
        self.voyage_3_embedding_goal = schedule(ensure_voyage_3_embedding)
        self.save(update_fields=('voyage_3_embedding_goal',))

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
        text_unit.schedule_voyage_3_embedding()
        return text_unit


def ensure_voyage_3_embedding(goal):
    text_unit = goal.textunit
    if text_unit.voyage_3_embedding:
        return AllDone()
    try:
        text_unit.voyage_3_embedding = get_embedding(text_unit.content)
    except voyageai.error.RateLimitError:
        return RetryMeLater(
            message='Voyage AI rate limit exceeded',
            precondition_date=timezone.now() + timezone.timedelta(minutes=1),
        )
    text_unit.save(update_fields=('voyage_3_embedding',))
    return AllDone()


def get_embedding(content):
    response = voyage_client.embed([content], model='voyage-3')
    return response.embeddings[0]


voyage_client = voyageai.Client(
    api_key=settings.VOYAGE_API_KEY,
)
