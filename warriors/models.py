import hashlib
import uuid

import openai
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Warrior(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    body = models.TextField(
        max_length=1000,
        blank=True,
    )
    body_sha_256 = models.BinaryField(
        max_length=32,
        unique=True,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )
    name = models.CharField(
        max_length=100,
        blank=True,
    )
    author = models.CharField(
        max_length=100,
        blank=True,
    )
    elo = models.FloatField(
        default=0.0,
        db_index=True,
    )

    class Meta:
        ordering = ('-elo',)

    def __str__(self):
        return self.name or str(self.id)

    def save(self, *args, **kwargs):
        self.body_sha_256 = hashlib.sha256(self.body.encode('utf-8')).digest()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('warrior_detail', args=[str(self.id)])


class Battle(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )
    warrior_1 = models.ForeignKey(
        to=Warrior,
        related_name='warrior1',
        on_delete=models.CASCADE,
    )
    warrior_2 = models.ForeignKey(
        to=Warrior,
        related_name='warrior2',
        on_delete=models.CASCADE,
    )
    result_1_2 = models.TextField(
        max_length=1000,
        blank=True,
    )
    result_2_1 = models.TextField(
        max_length=1000,
        blank=True,
    )
    llm_version = models.CharField(
        max_length=100,
    )

    class Meta:
        ordering = ('-created_at',)


openai_client = openai.Client(
    api_key=settings.OPENAI_API_KEY,
)


def perform_battle(warrior_1, warrior_2, save=True, now=None):
    if now is None:
        now = timezone.now()
    prompt = warrior_1.body + warrior_2.body
    model = 'gpt-3.5-turbo'
    response = openai_client.chat.completions.create(
        messages=[
            {'role': 'user', 'message': prompt},
        ],
        model='gpt-3.5-turbo',
        temperature=0,
        max_tokens=1000,
    )
    (resp_choice,) = response.choices
    battle = Battle(
        warrior_1=warrior_1,
        warrior_2=warrior_2,
        result_1_2=resp_choice.message,
        llm_version=model + '/' + resp_choice.fingerprint,
        created_at=now,
    )
    if save:
        battle.save()
    return battle
