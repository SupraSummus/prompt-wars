import datetime
import random
import uuid
from functools import cached_property, lru_cache
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.functions import TransactionNow
from django.contrib.sites.models import Site
from django.core.signing import BadSignature, Signer
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Abs
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from django_goals.models import schedule

from .lcs import lcs_ranges
from .rating import GameScore, get_expected_game_score, get_performance_rating


MAX_WARRIOR_LENGTH = 1000

MATCHMAKING_MAX_RATING_DIFF = 100  # rating diff of 100 means expected score is 64%
MAX_ALLOWED_RATING_PER_GAME = 100

# once two warriors battled we want to wait for a while before they can be matched again
MATCHMAKING_COOLDOWN = datetime.timedelta(days=91)

M_ELO_K = 1


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


class WarriorQuerySet(models.QuerySet):
    def battleworthy(self):
        return self.filter(
            moderation_passed=True,
        )


class Warrior(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    arena = models.ForeignKey(
        to=Arena,
        on_delete=models.CASCADE,
    )
    body = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
    )
    body_sha_256 = models.BinaryField(
        max_length=32,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(
        max_length=40,
        blank=True,
    )
    author_name = models.CharField(
        max_length=40,
        blank=True,
    )

    rating = models.FloatField(
        default=0.0,
    )
    rating_playstyle = ArrayField(
        size=M_ELO_K * 2,
        base_field=models.FloatField(),
        default=list,
    )
    rating_fit_loss = models.FloatField(
        default=0.0,
    )
    games_played = models.PositiveIntegerField(
        default=0,
    )

    moderation_date = models.DateTimeField(
        null=True,
        blank=True,
    )
    moderation_passed = models.BooleanField(
        null=True,
    )
    moderation_model = models.CharField(
        max_length=100,
        blank=True,
    )

    next_battle_schedule = models.DateTimeField(
        null=True,
        blank=True,
    )
    rating_error = models.FloatField(
        default=0.0,
    )

    public_battle_results = models.BooleanField(
        default=False,
        help_text=_("Indicates whether battle results should be public for this warrior."),
    )

    @property
    def rating_error_abs(self):
        return abs(self.rating_error)

    users = models.ManyToManyField(
        to=settings.AUTH_USER_MODEL,
        through='WarriorUserPermission',
        related_name='warriors',
    )

    objects = WarriorQuerySet.as_manager()
    secret_signer = Signer(salt='warrior')

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(
                check=models.Q(body_sha_256=models.Func(
                    models.Func(
                        models.F('body'),
                        models.Value('utf-8'),
                        function='convert_to',
                    ),
                    function='sha256',
                )),
                name='body_sha_256',
            ),
            models.UniqueConstraint(
                fields=['arena_id', 'body_sha_256'],
                name='arena_body_sha_256_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=['rating'],
                name='rating_index',
                condition=models.Q(moderation_passed=True),
            ),
            models.Index(
                Abs('rating_error'),
                name='rating_error_index',
            ),
            models.Index(
                fields=['next_battle_schedule'],
                name='next_battle_schedule_index',
                condition=models.Q(next_battle_schedule__isnull=False),
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

    def schedule_battle(self, now=None, **kwargs):
        if now is None:
            now = timezone.now()

        opponent = self.find_opponent(**kwargs)

        if opponent is None:
            self.next_battle_schedule = now + self.get_next_battle_delay()
            self.save(update_fields=['next_battle_schedule'])
            return None

        return self.create_battle(opponent)

    def create_battle(self, opponent):
        battle = Battle.create_from_warriors(self, opponent)
        self.next_battle_schedule = None
        opponent.next_battle_schedule = None
        Warrior.objects.bulk_update(
            [self, opponent],
            ['next_battle_schedule'],
        )
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
        battle_worthy_qs = Warrior.objects.battleworthy()
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
            id__in=historic_battles.values('warrior_1'),
        ).exclude(
            id__in=historic_battles.values('warrior_2'),
        )

    def get_next_battle_delay(self):
        # delay = max(
        #   K ** (games_played jittered) - 1,
        #   0,
        # ) * time unit
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

    def update_rating(self):
        """
        Compute rating based on games played.

        We assume all battles form a tournament.
        """
        # compute rating
        scores = {}  # opponent_id -> GameScore(score, opponent_rating, opponent_playstyle)
        games_played = 0
        for b in Battle.objects.with_warrior(self).resolved().select_related(
            'warrior_1',
            'warrior_2',
        ):
            b = b.get_warrior_viewpoint(self)
            if (game_score := b.score) is not None:
                normalize_playstyle_len(b.warrior_2.rating_playstyle)
                scores[b.warrior_2.id] = GameScore(
                    score=game_score,
                    opponent_rating=b.warrior_2.rating,
                    opponent_playstyle=b.warrior_2.rating_playstyle,
                )
            games_played += 1

        # we limit rating range for warriors with few games played
        max_allowed_rating = MAX_ALLOWED_RATING_PER_GAME * len(scores)
        normalize_playstyle_len(self.rating_playstyle)
        new_rating, new_playstyle, self.rating_fit_loss = get_performance_rating(
            list(scores.values()),
            allowed_rating_range=max_allowed_rating,
            rating_guess=self.rating,
            playstyle_guess=self.rating_playstyle,
            k=M_ELO_K,
        )
        rating_error = new_rating - self.rating

        # update related warriors
        if rating_error and len(scores) > 0:
            error_per_opponent = rating_error / len(scores) / 2
            Warrior.objects.filter(id__in=scores.keys()).update(
                rating=F('rating') - error_per_opponent,
                rating_error=F('rating_error') + error_per_opponent,
            )

        self.rating_error = 0.0
        self.rating += rating_error / 2
        self.rating_playstyle = new_playstyle
        self.games_played = games_played
        self.save(update_fields=[
            'rating', 'rating_playstyle',
            'rating_fit_loss',
            'games_played', 'rating_error',
        ])

        return rating_error

    def update_public_battle_results(self):
        """Recompute public_battle_results based on per user data"""
        user_permissions = list(WarriorUserPermission.objects.filter(
            warrior=self,
        ))
        if user_permissions:
            self.public_battle_results = any(
                up.public_battle_results
                for up in user_permissions
            )
            self.save(update_fields=['public_battle_results'])

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
        return self.users.filter(id=user.id).exists()


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
            models.Q(warrior_1=warrior) | models.Q(warrior_2=warrior),
        )

    def with_warriors(self, warrior_1, warrior_2):
        if warrior_1.id > warrior_2.id:
            warrior_1, warrior_2 = warrior_2, warrior_1
        return self.filter(
            warrior_1=warrior_1,
            warrior_2=warrior_2,
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
            Q(warrior_1__users=user) |  # noqa: W504
            Q(warrior_2__users=user)
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
        max_length=MAX_WARRIOR_LENGTH,
        blank=True,
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

    result_2_1 = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
        blank=True,
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

    rating_transferred_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    objects = BattleQuerySet.as_manager()

    class Meta:
        ordering = (
            '-rating_transferred_at',  # nulls first, then most recent
            '-scheduled_at',
        )
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    warrior_1_id__lt=models.F('warrior_2_id'),
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
            warrior_1=warrior_1,
            warrior_2=warrior_2,
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
        normalize_playstyle_len(self.warrior_1.rating_playstyle)
        normalize_playstyle_len(self.warrior_2.rating_playstyle)
        return score - get_expected_game_score(
            self.warrior_1.rating,
            self.warrior_1.rating_playstyle,
            self.warrior_2.rating,
            self.warrior_2.rating_playstyle,
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
        return self.warrior_1.public_battle_results or self.warrior_2.public_battle_results

    def get_warrior_viewpoint(self, warrior):
        """Return Battle such that warrior_1 == warrior"""
        if warrior == self.warrior_1:
            return self
        elif warrior == self.warrior_2:
            return Battle(
                id=self.id,
                arena=self.arena,
                scheduled_at=self.scheduled_at,
                warrior_1=self.warrior_2,
                warrior_2=self.warrior_1,

                result_1_2=self.result_2_1,
                lcs_len_1_2_1=self.lcs_len_2_1_2,
                lcs_len_1_2_2=self.lcs_len_2_1_1,
                finish_reason_1_2=self.finish_reason_2_1,
                llm_version_1_2=self.llm_version_2_1,
                resolved_at_1_2=self.resolved_at_2_1,

                result_2_1=self.result_1_2,
                lcs_len_2_1_1=self.lcs_len_1_2_2,
                lcs_len_2_1_2=self.lcs_len_1_2_1,
                finish_reason_2_1=self.finish_reason_1_2,
                llm_version_2_1=self.llm_version_1_2,
                resolved_at_2_1=self.resolved_at_1_2,

                rating_transferred_at=self.rating_transferred_at,

                game_1_id=self.game_2_id,
                game_2_id=self.game_1_id,
            )


def normalize_playstyle_len(playstyle):
    # Make sure playstyle vector is of fixed length.
    # This is used to automatically migrate data from different versions of M_ELO_K.
    # Also by default playstyle is initialized as empty array, so this functions as a default value.
    while len(playstyle) < M_ELO_K * 2:
        playstyle.append(random.random())
    while len(playstyle) > M_ELO_K * 2:
        playstyle.pop()
    assert len(playstyle) == M_ELO_K * 2


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
            'result',
            'finish_reason',
            'llm_version',
            'resolved_at',
        ):
            return f'{field_name}_{self.direction}'
        elif field_name == 'lcs_len_1':
            return f'lcs_len_{self.direction}_{self.direction_from}'
        elif field_name == 'lcs_len_2':
            return f'lcs_len_{self.direction}_{self.direction_to}'
        elif field_name == 'warrior_1':
            return f'warrior_{self.direction_from}'
        elif field_name == 'warrior_2':
            return f'warrior_{self.direction_to}'
        elif field_name == 'arena':
            return field_name
        else:
            return None

    @property
    def warrior_1_preserved_ratio(self):
        return self.lcs_len_1 / max(
            len(self.warrior_1.body),
            len(self.result),
        )

    @property
    def warrior_2_preserved_ratio(self):
        return self.lcs_len_2 / max(
            len(self.warrior_2.body),
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
        return lcs_mark(self.result, self.warrior_1.body)

    @cached_property
    def result_marked_for_2(self):
        return lcs_mark(self.result, self.warrior_2.body)


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
