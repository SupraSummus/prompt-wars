import secrets
import uuid

from django.db import models
from django.utils import timezone
from pgvector.django import BitField

from embedding_explorer.models import EMBEDDING_BITS, ExplorerQuery


def _random_bits():
    """Return a random 2048-bit string for use as a GuessingTarget embedding."""
    return bin(secrets.randbits(EMBEDDING_BITS))[2:].zfill(EMBEDDING_BITS)


class GuessingTarget(models.Model):
    """A randomly-generated secret embedding that players try to match."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    embedding = BitField(length=EMBEDDING_BITS, default=_random_bits)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Guess(models.Model):
    """A player's guess for a GuessingTarget, linked to an ExplorerQuery."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    target = models.ForeignKey(
        GuessingTarget,
        on_delete=models.CASCADE,
        related_name='guesses',
    )
    query = models.ForeignKey(
        ExplorerQuery,
        on_delete=models.CASCADE,
        related_name='guesses',
    )
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='guesses',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['target', 'query', 'user'],
                name='guess_target_query_user_unique',
            ),
        ]

    def __str__(self):
        return f'{self.query.phrase!r} → {self.target.name}'
