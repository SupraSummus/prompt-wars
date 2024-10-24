import datetime
import random
import uuid
from functools import cached_property, lru_cache
from urllib.parse import urlencode

import numpy
from django.conf import settings
from django.contrib.postgres.functions import TransactionNow
from django.contrib.sites.models import Site
from django.core.signing import BadSignature, Signer
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from django_goals.models import schedule

from .lcs import lcs_ranges
from .rating import get_expected_game_score
from .rating_models import M_ELO_K, RatingMixin, normalize_playstyle_len
from .stats import ArenaStats
from .text_unit import TextUnit
from .warriors import MAX_WARRIOR_LENGTH, Warrior


__all__ = ['ArenaStats', 'Warrior', 'TextUnit']


MATCHMAKING_MAX_RATING_DIFF = 100  # rating diff of 100 means expected score is 64%

# once two warriors battled we want to wait for a while before they can be matched again
MATCHMAKING_COOLDOWN = datetime.timedelta(days=122)  # 4 months


class LLM(models.TextChoices):
    GPT_3_5_TURBO = 'gpt-3.5-turbo', 'GPT-3.5 Turbo'  # TODO: remove
    OPENAI_GPT = 'openai-gpt', _('OpenAI GPT')
    CLAUDE_3_HAIKU = 'claude-3-haiku', _('Claude 3 Haiku')


class Arena(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    site = models.OneToOneField(
        to=Site,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    name = models.CharField(
        max_length=40,
        unique=True,
    )
    listed = models.BooleanField(
        default=False,
    )
    llm = models.CharField(
        max_length=20,
        choices=LLM.choices,
    )
    prompt = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
        blank=True,
    )
    description = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class WarriorArenaQuerySet(models.QuerySet):
    def battleworthy(self):
        return self.filter(
            warrior__moderation_passed=True,
        )


class WarriorArena(RatingMixin, models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    warrior = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='warrior_arenas',
    )
    arena = models.ForeignKey(
        to=Arena,
        on_delete=models.CASCADE,
        related_name='warriors',
    )

    @property
    def body(self):
        return self.warrior.body

    @property
    def body_sha_256(self):
        return self.warrior.body_sha_256

    @property
    def created_at(self):
        return self.warrior.created_at

    @property
    def created_by(self):
        return self.warrior.created_by

    @property
    def name(self):
        return self.warrior.name

    @property
    def author_name(self):
        return self.warrior.author_name

    games_played = models.PositiveIntegerField(
        default=0,
    )

    @property
    def moderation_date(self):
        return self.warrior.moderation_date

    @property
    def moderation_passed(self):
        return self.warrior.moderation_passed

    @property
    def moderation_model(self):
        return self.warrior.moderation_model

    @property
    def public_battle_results(self):
        return self.warrior.public_battle_results

    next_battle_schedule = models.DateTimeField(
        default=timezone.now,
    )

    @property
    def rating_error_abs(self):
        return abs(self.rating_error)

    objects = WarriorArenaQuerySet.as_manager()
    secret_signer = Signer(salt='warrior')

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=['arena', 'warrior'],
                name='arena_warrior_unique',
            ),
        ]
        indexes = [
            *RatingMixin.Meta.indexes,
            models.Index(
                fields=['next_battle_schedule'],
                name='next_battle_schedule_index',
                condition=models.Q(moderation_passed=True),
            ),
        ]

    def __str__(self):
        if self.moderation_passed is not True:
            return str(self.id)
        return self.name or str(self.id)

    def get_absolute_url(self):
        return reverse('warrior_detail', args=[str(self.id)])

    def get_absolute_url_secret(self):
        return self.get_absolute_url() + '?' + urlencode({
            'secret': self.secret,
        })

    def create_battle(self, opponent, now=None):
        if now is None:
            now = timezone.now()

        battle = Battle.create_from_warriors(self, opponent)

        self.games_played = Battle.objects.with_warrior(self).count()
        self.next_battle_schedule = now + self.get_next_battle_delay()
        self.save(update_fields=[
            'games_played',
            'next_battle_schedule',
        ])

        opponent.games_played = Battle.objects.with_warrior(opponent).count()
        opponent.save(update_fields=['games_played'])

        # Generate voyage 3 embeddings in case not already generated.
        # Normally we generate them when warrior is created.
        # This is for old warriors created before we introduced embeddings.
        # Possibly this can be removed in the future.
        self.warrior.schedule_voyage_3_embedding()
        opponent.warrior.schedule_voyage_3_embedding()

        return battle

    def find_opponent(self, **kwargs):
        return self.find_opponents(**kwargs).order_by('?').select_for_update(
            no_key=True,
            skip_locked=True,
        ).first()

    def find_opponents(
        self,
        max_rating_diff=MATCHMAKING_MAX_RATING_DIFF,
    ):
        battle_worthy_qs = WarriorArena.objects.battleworthy()
        top_rating = self.rating + max_rating_diff
        bottom_rating = self.rating - max_rating_diff

        historic_battles = Battle.objects.with_warrior(self).recent()

        return battle_worthy_qs.filter(
            arena_id=self.arena_id,
            rating__lt=top_rating,
            rating__gt=bottom_rating,
        ).exclude(
            id=self.id,
        ).exclude(
            id__in=historic_battles.values('warrior_arena_1'),
        ).exclude(
            id__in=historic_battles.values('warrior_arena_2'),
        )

    def get_next_battle_delay(self):
        """
        Get delay to the game N+1, where N is the number of games with this warrior.
        Games are exponentially less and less frequent.
        """
        K = 2
        time_unit = datetime.timedelta(minutes=1)
        exponent = self.games_played - random.random()
        if exponent > 25:
            # avoid overflow
            exponent = 25
        return max(
            K ** exponent - 1,
            0,
        ) * time_unit

    @cached_property
    def secret(self):
        return self.secret_signer.sign(str(self.id)).split(':')[1]

    def is_secret_valid(self, key):
        full_key = f'{self.id}:{key}'
        try:
            self.secret_signer.unsign(full_key)
            return True
        except BadSignature:
            return False

    @lru_cache(maxsize=16)
    def is_user_authorized(self, user):
        if not user.is_authenticated:
            return False
        return WarriorUserPermission.objects.filter(
            warrior=self.warrior,
            user=user,
        ).exists()


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


class BattleQuerySet(models.QuerySet):
    def with_warrior(self, warrior):
        return self.filter(
            models.Q(warrior_arena_1=warrior) |
            models.Q(warrior_arena_2=warrior),
        )

    def with_warriors(self, warrior_1, warrior_2):
        if warrior_1.id > warrior_2.id:
            warrior_1, warrior_2 = warrior_2, warrior_1
        return self.filter(
            warrior_arena_1=warrior_1,
            warrior_arena_2=warrior_2,
        )

    def resolved(self):
        """Battles that are fully computed"""
        return self.exclude(
            resolved_at_1_2=None,
        ).exclude(
            resolved_at_2_1=None,
        )

    def for_user(self, user):
        if not user.is_authenticated:
            return self
        return self.filter(
            Q(warrior_arena_1__warrior__users=user) |
            Q(warrior_arena_2__warrior__users=user),
        ).distinct()

    def recent(self):
        return self.filter(
            scheduled_at__gt=timezone.now() - MATCHMAKING_COOLDOWN,
        )


class Battle(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    arena = models.ForeignKey(
        to=Arena,
        on_delete=models.CASCADE,
    )
    scheduled_at = models.DateTimeField(
        db_index=True,
        default=timezone.now,
    )
    warrior_arena_1 = models.ForeignKey(
        to=WarriorArena,
        related_name='warrior1',
        on_delete=models.CASCADE,
    )
    warrior_arena_2 = models.ForeignKey(
        to=WarriorArena,
        related_name='warrior2',
        on_delete=models.CASCADE,
    )

    text_unit_1_2 = models.ForeignKey(
        to=TextUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    lcs_len_1_2_1 = models.PositiveIntegerField(
        default=0.0,
    )
    lcs_len_1_2_2 = models.PositiveIntegerField(
        default=0.0,
    )
    finish_reason_1_2 = models.CharField(
        max_length=20,
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

    text_unit_2_1 = models.ForeignKey(
        to=TextUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    lcs_len_2_1_1 = models.PositiveIntegerField(
        default=0.0,
    )
    lcs_len_2_1_2 = models.PositiveIntegerField(
        default=0.0,
    )
    finish_reason_2_1 = models.CharField(
        max_length=20,
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

    # rating_transferred_at is not used anymore
    rating_transferred_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    objects = BattleQuerySet.as_manager()

    class Meta:
        ordering = (
            '-scheduled_at',
        )
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    warrior_arena_1_id__lt=models.F('warrior_arena_2_id'),
                ),
                name='warrior_ordering',
            ),
        ]

    @classmethod
    def create_from_warriors(cls, warrior_1, warrior_2):
        assert warrior_1.arena_id == warrior_2.arena_id
        if warrior_1.id > warrior_2.id:
            warrior_1, warrior_2 = warrior_2, warrior_1
        battle = cls.objects.create(
            arena_id=warrior_1.arena_id,
            warrior_arena_1=warrior_1,
            warrior_arena_2=warrior_2,
            scheduled_at=TransactionNow(),
        )
        from .tasks import (
            resolve_battle_1_2, resolve_battle_2_1, transfer_rating,
        )
        resolve_1_2_goal = schedule(
            resolve_battle_1_2,
            args=(str(battle.id),),
        )
        resolve_2_1_goal = schedule(
            resolve_battle_2_1,
            args=(str(battle.id),),
        )
        schedule(
            transfer_rating,
            args=(str(battle.id),),
            precondition_goals=[resolve_1_2_goal, resolve_2_1_goal],
        )

        return battle

    def __init__(self, *args, game_1_id='1_2', game_2_id='2_1', **kwargs):
        super().__init__(*args, **kwargs)
        self.game_1_id = game_1_id
        self.game_2_id = game_2_id

    def get_absolute_url(self):
        return reverse('battle_detail', args=[str(self.id)])

    @property
    def score(self):
        '''
        Score of warrior 1
        Score of warrior 2 is `1 - score`
        '''
        game_1_2_score = self.game_1_2.score
        game_2_1_score = self.game_2_1.score_rev
        if game_1_2_score is None or game_2_1_score is None:
            return None
        return (game_1_2_score + game_2_1_score) / 2

    @property
    def performance(self):
        '''
        How well warrior 1 performed in this battle adjusted the strength of both warriors.
        '''
        score = self.score
        if score is None:
            return None
        normalize_playstyle_len(self.warrior_arena_1.rating_playstyle)
        normalize_playstyle_len(self.warrior_arena_2.rating_playstyle)
        return score - get_expected_game_score(
            self.warrior_arena_1.rating,
            self.warrior_arena_1.rating_playstyle,
            self.warrior_arena_2.rating,
            self.warrior_arena_2.rating_playstyle,
            k=M_ELO_K,
        )

    @property
    def performance_str(self):
        performance = self.performance
        if performance is None:
            return 'none'
        return f'{performance:+.2f}'

    @cached_property
    def game_1_2(self):
        return Game(self, '1_2')

    @cached_property
    def game_2_1(self):
        return Game(self, '2_1')

    @property
    def public_battle_results(self):
        return (
            self.warrior_arena_1.public_battle_results or
            self.warrior_arena_2.public_battle_results
        )

    def get_warrior_viewpoint(self, warrior):
        """Return Battle such that warrior_arena_1 == warrior"""
        if warrior == self.warrior_arena_1:
            return self
        elif warrior == self.warrior_arena_2:
            return Battle(
                id=self.id,
                arena=self.arena,
                scheduled_at=self.scheduled_at,
                warrior_arena_1=self.warrior_arena_2,
                warrior_arena_2=self.warrior_arena_1,

                text_unit_1_2=self.text_unit_2_1,
                lcs_len_1_2_1=self.lcs_len_2_1_2,
                lcs_len_1_2_2=self.lcs_len_2_1_1,
                finish_reason_1_2=self.finish_reason_2_1,
                llm_version_1_2=self.llm_version_2_1,
                resolved_at_1_2=self.resolved_at_2_1,

                text_unit_2_1=self.text_unit_1_2,
                lcs_len_2_1_1=self.lcs_len_1_2_2,
                lcs_len_2_1_2=self.lcs_len_1_2_1,
                finish_reason_2_1=self.finish_reason_1_2,
                llm_version_2_1=self.llm_version_1_2,
                resolved_at_2_1=self.resolved_at_1_2,

                rating_transferred_at=self.rating_transferred_at,

                game_1_id=self.game_2_id,
                game_2_id=self.game_1_id,
            )


class Game:
    def __init__(self, battle, direction):
        '''
        :param battle: Battle
        :param direction: str '1_2' or '2_1'
        '''
        assert direction in ('1_2', '2_1')
        self.battle = battle
        self.direction = direction
        self.direction_from, self.direction_to = direction.split('_')

    def __getattr__(self, field_name):
        mapped_name = self.map_field_name(field_name)
        if mapped_name is not None:
            return getattr(
                self.battle,
                self.map_field_name(field_name),
            )
        else:
            return super().__getattribute__(field_name)

    def __setattr__(self, field_name, value):
        mapped_name = self.map_field_name(field_name)
        if mapped_name is not None:
            setattr(
                self.battle,
                self.map_field_name(field_name),
                value,
            )
        else:
            super().__setattr__(field_name, value)

    def save(self, update_fields):
        self.battle.save(update_fields=[
            self.map_field_name(f) for f in update_fields
        ])

    def map_field_name(self, field_name):
        if field_name in (
            'text_unit',
            'finish_reason',
            'llm_version',
            'resolved_at',
        ):
            return f'{field_name}_{self.direction}'
        elif field_name == 'lcs_len_1':
            return f'lcs_len_{self.direction}_{self.direction_from}'
        elif field_name == 'lcs_len_2':
            return f'lcs_len_{self.direction}_{self.direction_to}'
        elif field_name == 'warrior_arena_1':
            return f'warrior_arena_{self.direction_from}'
        elif field_name == 'warrior_arena_2':
            return f'warrior_arena_{self.direction_to}'
        elif field_name == 'arena':
            return field_name
        else:
            return None

    @property
    def result(self):
        if self.text_unit is None:
            return ''
        return self.text_unit.content

    @property
    def warrior_1_preserved_ratio(self):
        return self.lcs_len_1 / max(
            len(self.warrior_arena_1.body),
            len(self.result),
        )

    @property
    def warrior_2_preserved_ratio(self):
        return self.lcs_len_2 / max(
            len(self.warrior_arena_2.body),
            len(self.result),
        )

    @property
    def score(self):
        '''
        Score of warrior 1
        Score of warrior 2 is `1 - score`
        '''
        if self.finish_reason == 'error':
            return None
        s1 = self.warrior_1_preserved_ratio
        s2 = self.warrior_2_preserved_ratio
        if s1 + s2 == 0:
            return 0.5
        return s1 / (s1 + s2)

    @property
    def score_rev(self):
        score = self.score
        if score is None:
            return None
        return 1.0 - score

    @cached_property
    def result_marked_for_1(self):
        return lcs_mark(self.result, self.warrior_arena_1.body)

    @cached_property
    def result_marked_for_2(self):
        return lcs_mark(self.result, self.warrior_arena_2.body)

    @cached_property
    def warrior_1_similarity(self):
        return _warrior_similarity(self.text_unit, self.warrior_arena_1.warrior)

    @cached_property
    def warrior_2_similarity(self):
        return _warrior_similarity(self.text_unit, self.warrior_arena_2.warrior)

    @property
    def warrior_1_similarity_relative(self):
        return _softmax(self.warrior_1_similarity, [self.warrior_1_similarity, self.warrior_2_similarity])

    @property
    def warrior_2_similarity_relative(self):
        return _softmax(self.warrior_2_similarity, [self.warrior_1_similarity, self.warrior_2_similarity])


def lcs_mark(result, warrior_body):
    mark_ranges = lcs_ranges(result, warrior_body)
    i = 0
    parts = []
    for start, end in mark_ranges:
        unmarked = result[i:start]
        marked = result[start:end]
        i = end
        parts.append(format_html(
            '{}<mark>{}</mark>',
            escape(unmarked),
            escape(marked),
        ))
    parts.append(escape(result[i:]))
    return mark_safe(''.join(parts))


def _warrior_similarity(text_unit, warrior):
    if (
        not text_unit or
        not text_unit.voyage_3_embedding or
        not warrior.voyage_3_embedding
    ):
        return None
    result_embedding = numpy.array(text_unit.voyage_3_embedding)
    warrior_embedding = numpy.array(warrior.voyage_3_embedding)
    return numpy.dot(result_embedding, warrior_embedding)


def _softmax(value, values):
    if any(v is None for v in values):
        return None
    return numpy.exp(value) / sum(numpy.exp(v) for v in values)
