import hashlib
import math
import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone

from .lcs import lcs_len


MAX_WARRIOR_LENGTH = 1000


class Warrior(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    body = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
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
    rating = models.FloatField(
        db_index=True,
        default=0.0,
    )
    next_battle_schedule = models.DateTimeField(
        db_index=None,
        default=None,
    )

    class Meta:
        ordering = ('-rating',)

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
    scheduled_at = models.DateTimeField(
        default=timezone.now,
    )
    warrior_1 = models.ForeignKey(
        to=Warrior,
        related_name='warrior1',
        on_delete=models.CASCADE,
    )
    warrior_1_rating = models.FloatField()
    warrior_2 = models.ForeignKey(
        to=Warrior,
        related_name='warrior2',
        on_delete=models.CASCADE,
    )
    warrior_2_rating = models.FloatField()

    result_1_2 = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
        blank=True,
    )
    llm_version_1_2 = models.CharField(
        max_length=100,
        blank=True,
    )
    resolved_at_1_2 = models.DateTimeField(
        null=True,
        blank=True,
    )

    result_2_1 = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
        blank=True,
    )
    llm_version_2_1 = models.CharField(
        max_length=100,
        blank=True,
    )
    resolved_at_2_1 = models.DateTimeField(
        null=True,
        blank=True,
    )

    rating_transferred_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ('-scheduled_at',)

    @property
    def rating_gained(self):
        '''
        Rating points transfered from warrior 2 to warrior 1
        '''
        return self.view_1.rating_gained - self.view_2.rating_gained

    @property
    def view_1(self):
        return BattleRelativeView(self, '1_2')

    @property
    def view_2(self):
        return BattleRelativeView(self, '2_1')


class BattleRelativeView:
    def __init__(self, battle, direction):
        '''
        :param battle: Battle
        :param direction: str '1_2' or '2_1'
        '''
        assert direction in ('1_2', '2_1')
        self.battle = battle
        self.direction = direction

    @property
    def warrior_1(self):
        return self.battle.warrior_1 if self.direction == '1_2' else self.battle.warrior_2

    @property
    def warrior_2(self):
        return self.battle.warrior_2 if self.direction == '1_2' else self.battle.warrior_1

    def __getattr__(self, field_name):
        return getattr(
            self.battle,
            self.map_field_name(field_name),
        )

    def __setattr__(self, field_name, value):
        return setattr(
            self.battle,
            self.map_field_name(field_name),
            value,
        )

    def save(self, update_fields):
        self.battle.save(update_fields=[
            self.map_field_name(f) for f in update_fields
        ])

    def map_field_name(self, field_name):
        assert field_name in (
            'result',
            'llm_version',
            'resolved_at',
        )
        return f'{field_name}_{self.direction}'

    @property
    def rating_gained(self):
        '''
        Rating points transfered from warrior 2 to warrior 1
        '''
        expected_score = 1 / (1 + math.exp(self.warrior_2_rating - self.warrior_1_rating))
        K = 1 / 16
        return K * (self.score - expected_score)

    @property
    def score(self):
        '''
        Score of warrior 1
        Score of warrior 2 is `1 - score`
        '''
        s1 = lcs_len(self.warrior_1.body, self.result) / len(self.warrior_1.body)
        s2 = lcs_len(self.warrior_2.body, self.result) / len(self.warrior_2.body)
        return s1 / (s1 + s2)
