import hashlib
import uuid

import requests
from django.db import models
from django.utils import timezone
from django_goals.models import AllDone, Goal, RetryMeLater, schedule
from pgvector.django import BitField


MAX_PHRASE_LENGTH = 100

EMBEDDING_BITS = 2048


class ExplorerQuery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    phrase = models.TextField(max_length=MAX_PHRASE_LENGTH)
    phrase_sha_256 = models.BinaryField(max_length=32, unique=True)
    embedding = BitField(length=EMBEDDING_BITS, null=True, blank=True)
    embedding_goal = models.OneToOneField(
        to=Goal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(phrase_sha_256=models.Func(
                    models.Func(
                        models.F('phrase'),
                        models.Value('utf-8'),
                        function='convert_to',
                    ),
                    function='sha256',
                )),
                name='explorer_query_phrase_sha_256',
            ),
        ]

    def __str__(self):
        return self.phrase

    @classmethod
    def get_or_create(cls, phrase):
        sha_256 = hashlib.sha256(phrase.encode('utf-8')).digest()
        query, created = cls.objects.get_or_create(
            phrase_sha_256=sha_256,
            defaults={'phrase': phrase},
        )
        query.schedule_embedding()
        return query

    def schedule_embedding(self):
        if self.embedding or self.embedding_goal:
            return
        self.embedding_goal = schedule(_ensure_embedding)
        self.save(update_fields=('embedding_goal',))


def _ensure_embedding(goal):
    from .voyage import get_voyage_embedding

    try:
        query = ExplorerQuery.objects.get(embedding_goal=goal)
    except ExplorerQuery.DoesNotExist:
        return AllDone()

    if query.embedding:
        return AllDone()

    try:
        query.embedding = get_voyage_embedding(query.phrase)
    except requests.RequestException:
        return RetryMeLater(
            message='Voyage AI request failed',
            precondition_date=timezone.now() + timezone.timedelta(minutes=1),
        )
    query.save(update_fields=('embedding',))
    return AllDone()
