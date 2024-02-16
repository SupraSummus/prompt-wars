import datetime
import math
import random
import uuid
from functools import cached_property, partial
from urllib.parse import urlencode

import django_q
from django.conf import settings
from django.contrib.postgres.functions import TransactionNow
from django.core.signing import BadSignature, Signer
from django.db import models, transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
from django_q.tasks import async_chain


MAX_WARRIOR_LENGTH = 1000
RATING_TRANSFER_COEFFICIENT = 0.3

# Matchaking max rating diff makes sure that equal players after one fully wins (scores 1) wont be matched again.
# 1. assume warriors of equal rating -> expected match score is 0.5
# 2. assume one of them wins fully -> scores 1, other scores 0
# 3. rating transfered is RATING_TRANSFER_COEFFICIENT * (1 - 0.5) -> their diff after the battle is twice that
MATCHMAKING_MAX_RATING_DIFF = RATING_TRANSFER_COEFFICIENT

# once to warriors battled we want to wait for a while before they can be matched again
MATCHMAKING_COOLDOWN = datetime.timedelta(days=28)


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
        db_index=True,
        default=0.0,
    )

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
        ]
        indexes = [
            models.Index(
                fields=['rating'],
                name='rating_index',
                condition=models.Q(moderation_flagged=False),
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

    def schedule_battle(self, now, **kwargs):
        opponent = self.find_opponent(**kwargs)

        if opponent is None:
            self.next_battle_schedule = now + self.get_next_battle_delay()
            self.save(update_fields=['next_battle_schedule'])
            return None

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
        cooldown=MATCHMAKING_COOLDOWN,
    ):
        battle_worthy_qs = Warrior.objects.battleworthy()
        top_rating = self.rating + max_rating_diff
        bottom_rating = self.rating - max_rating_diff

        historic_battles = Battle.objects.with_warrior(self).filter(
            scheduled_at__gt=timezone.now() - cooldown,
        )

        return battle_worthy_qs.filter(
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
        n = self.games_played - 1
        if n < 0:
            return datetime.timedelta()
        # add some jitter
        n -= random.random()
        if n > 25:
            n = 25
        return datetime.timedelta(
            minutes=2 ** n,
        )

    def update_rating(self, step=0.5):
        """
        Compute rating based on games played.

        We assume all battles form a tournament
        and starting rating of this warrior is previous rating.
        """
        new_rating = 0.0
        games_played = 0
        opponents = set()
        for b in Battle.objects.with_warrior(self).resolved().select_related(
            'warrior_1',
            'warrior_2',
        ):
            b = b.get_warrior_viewpoint(self)
            if b.rating_gained is not None:
                new_rating += b.rating_gained
            games_played += 1
            opponents.add(b.warrior_2.id)

        rating_error = abs(new_rating - self.rating) * step
        if rating_error > 0:
            Warrior.objects.filter(id__in=opponents).update(
                rating_error=F('rating_error') + rating_error / (F('games_played') + 1),
            )

        self.rating_error = 0.0  # this only moves current warrior back in the recalculating queue
        self.rating = self.rating * (1 - step) + new_rating * step
        self.games_played = games_played
        self.save(update_fields=['rating', 'games_played', 'rating_error'])

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
        )


class Battle(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
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
        if warrior_1.id > warrior_2.id:
            warrior_1, warrior_2 = warrior_2, warrior_1
        battle = cls.objects.create(
            warrior_1=warrior_1,
            warrior_2=warrior_2,
            scheduled_at=TransactionNow(),
        )

        from .tasks import resolve_battle, transfer_rating
        transaction.on_commit(partial(
            async_chain,
            [
                (resolve_battle, (battle.id, '1_2')),
                (resolve_battle, (battle.id, '2_1')),
                (transfer_rating, (battle.id,)),
            ],
            # by default it uses sync=False in non-configurable manner
            sync=django_q.conf.Conf.SYNC,
        ))

        return battle

    def __init__(self, *args, game_1_id='1_2', game_2_id='2_1', **kwargs):
        super().__init__(*args, **kwargs)
        self.game_1_id = game_1_id
        self.game_2_id = game_2_id

    @property
    def rating_gained(self):
        '''
        Rating points transfered from warrior 2 to warrior 1
        '''
        rating_1_2 = self.game_1_2.rating_gained
        rating_2_1 = self.game_2_1.rating_gained
        if rating_1_2 is None or rating_2_1 is None:
            return None
        return (rating_1_2 - rating_2_1) / 2

    @property
    def rating_gained_str(self):
        rating_gained = self.rating_gained
        if rating_gained is None:
            return 'none'
        return f'{rating_gained:+.3f}'

    @cached_property
    def game_1_2(self):
        return Game(self, '1_2')

    @cached_property
    def game_2_1(self):
        return Game(self, '2_1')

    def get_warrior_viewpoint(self, warrior):
        """Return Battle such that warrior_1 == warrior"""
        if warrior == self.warrior_1:
            return self
        elif warrior == self.warrior_2:
            return Battle(
                id=self.id,
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
        else:
            return None

    @property
    def rating_gained(self):
        '''
        Rating points transfered from warrior 2 to warrior 1.
        '''
        score = self.score
        if score is None:
            return None
        expected_score = 1 / (1 + math.exp(self.warrior_2.rating - self.warrior_1.rating))
        return RATING_TRANSFER_COEFFICIENT * (score - expected_score)

    @cached_property
    def score(self):
        '''
        Score of warrior 1
        Score of warrior 2 is `1 - score`
        '''
        if self.finish_reason == 'error':
            return None
        s1 = self.lcs_len_1 / max(
            len(self.warrior_1.body),
            len(self.result),
        )
        s2 = self.lcs_len_2 / max(
            len(self.warrior_2.body),
            len(self.result),
        )
        if s1 + s2 == 0:
            return 0.5
        return s1 / (s1 + s2)

    @property
    def score_rev(self):
        score = self.score
        if score is None:
            return None
        return 1.0 - score
