import datetime
import uuid
from functools import cached_property

from django.contrib.postgres.functions import TransactionNow
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from django_goals.models import schedule
from django_goals.utils import GoalRelatedMixin

from .lcs import lcs_ranges
from .rating import get_expected_game_score
from .rating_models import M_ELO_K, normalize_playstyle_len
from .score import ScoreAlgorithm
from .text_unit import TextUnit
from .warriors import Warrior


# once two warriors battled we want to wait for a while before they can be matched again
MATCHMAKING_COOLDOWN = datetime.timedelta(days=183)  # 6 months


class BattleQuerySet(models.QuerySet):
    def with_warrior_arena(self, warrior_arena):
        return self.filter(
            llm=warrior_arena.arena.llm,
        ).filter(
            models.Q(warrior_1_id=warrior_arena.warrior_id) |
            models.Q(warrior_2_id=warrior_arena.warrior_id),
        )

    def with_warrior_arenas(self, warrior_arena_1, warrior_arena_2):
        assert warrior_arena_1.arena_id == warrior_arena_2.arena_id
        warrior_1_id = warrior_arena_1.warrior_id
        warrior_2_id = warrior_arena_2.warrior_id
        if warrior_1_id > warrior_2_id:
            warrior_1_id, warrior_2_id = warrior_2_id, warrior_1_id
        return self.filter(
            llm=warrior_arena_1.arena.llm,
            warrior_1_id=warrior_1_id,
            warrior_2_id=warrior_2_id,
        )

    def resolved(self):
        """Battles that are fully computed: every game of theirs is resolved."""
        return self.exclude(games__resolved_at=None)

    def for_user(self, user):
        if not user.is_authenticated:
            return self
        return self.filter(
            Q(warrior_1__users=user) |
            Q(warrior_2__users=user),
        ).distinct()

    def recent(self):
        return self.filter(
            scheduled_at__gt=timezone.now() - MATCHMAKING_COOLDOWN,
        )


class LLM(models.TextChoices):
    OPENAI_GPT = 'openai-gpt', _('OpenAI GPT')
    CLAUDE_3_HAIKU = 'claude-3-haiku', _('Anthropic Claude')
    GOOGLE_GEMINI = 'google-gemini', _('Google Gemini')


class Battle(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    arena = models.ForeignKey(
        to='Arena',
        on_delete=models.CASCADE,
        null=True,
    )
    llm = models.CharField(
        max_length=20,
        choices=LLM.choices,
    )
    scheduled_at = models.DateTimeField(
        db_index=True,
        default=timezone.now,
    )
    warrior_1 = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='+',
    )
    warrior_2 = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='+',
    )

    objects = BattleQuerySet.as_manager()

    class Meta:
        ordering = (
            '-scheduled_at',
        )
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    warrior_1_id__lt=models.F('warrior_2_id'),
                ),
                name='warrior_ordering',
            ),
        ]

    @classmethod
    def create_from_warriors(cls, warrior_arena_1, warrior_arena_2):
        assert warrior_arena_1.arena_id == warrior_arena_2.arena_id
        arena_id = warrior_arena_1.arena_id

        warrior_1 = warrior_arena_1.warrior
        warrior_2 = warrior_arena_2.warrior
        if warrior_1.id > warrior_2.id:
            warrior_1, warrior_2 = warrior_2, warrior_1

        from .tasks import (
            resolve_battle_1_2, resolve_battle_2_1, transfer_rating,
        )

        # battle.scheduled_at is an unevaluated TransactionNow() that the
        # game inserts re-send, so the three timestamps (asserted equal in
        # resolve_battle) only match inside one transaction — which also
        # ensures a battle never exists without its two games.
        with transaction.atomic():
            battle = cls.objects.create(
                arena_id=arena_id,
                llm=warrior_arena_1.arena.llm,
                warrior_1=warrior_1,
                warrior_2=warrior_2,
                scheduled_at=TransactionNow(),
            )
            resolve_1_2_goal = schedule(
                resolve_battle_1_2,
                args=(str(battle.id),),
            )
            resolve_2_1_goal = schedule(
                resolve_battle_2_1,
                args=(str(battle.id),),
            )
            db_game_1_2 = DBGame.objects.create(
                battle=battle,
                llm=warrior_arena_1.arena.llm,
                warrior_1=warrior_1,
                warrior_2=warrior_2,
                scheduled_at=battle.scheduled_at,
                processed_goal=resolve_1_2_goal,
            )
            db_game_2_1 = DBGame.objects.create(
                battle=battle,
                llm=warrior_arena_1.arena.llm,
                warrior_1=warrior_2,
                warrior_2=warrior_1,
                scheduled_at=battle.scheduled_at,
                processed_goal=resolve_2_1_goal,
            )

            schedule(
                transfer_rating,
                args=(str(battle.id),),
                precondition_goals=[resolve_1_2_goal, resolve_2_1_goal],
            )

        return battle, db_game_1_2, db_game_2_1

    def get_absolute_url(self):
        return reverse('battle_detail', args=[str(self.id)])

    @cached_property
    def games_list(self):
        """
        The battle's games, the one its first warrior leads first.

        The canonical pair is the one game order
        that does not depend on who is looking.
        """
        return tuple(sorted(
            self.games.all(),
            key=lambda game: game.warrior_1_id != self.warrior_1_id,
        ))

    def warrior_score(self, warrior_id, algorithm=ScoreAlgorithm.LCS):
        """
        One warrior's score in this battle: the mean over its games.

        Pending until every game is scored,
        so the number a reader sees is the number rating fits against
        ("A battle score is pending until every game resolves"
        in docs/battle-display.md).
        Scores of the two warriors sum to 1.
        """
        scores = []
        for game in self.games_list:
            score_object = game.score_object(algorithm)
            if score_object is None:
                return None
            score = score_object.score_for(warrior_id)
            if score is None:
                return None
            scores.append(score)
        if not scores:
            return None
        return sum(scores) / len(scores)

    def warrior_performance(self, warrior_arena, opponent_arena, algorithm=ScoreAlgorithm.LCS):
        """
        How well a warrior did here, adjusted for the strength of both.

        Pairwise by construction: the expectation it subtracts
        is defined for two warriors and for no wider battle.
        """
        score = self.warrior_score(warrior_arena.warrior_id, algorithm)
        if score is None:
            return None
        normalize_playstyle_len(warrior_arena.rating_playstyle)
        normalize_playstyle_len(opponent_arena.rating_playstyle)
        return score - get_expected_game_score(
            warrior_arena.rating,
            warrior_arena.rating_playstyle,
            opponent_arena.rating,
            opponent_arena.rating_playstyle,
            k=M_ELO_K,
        )

    @property
    def public_battle_results(self):
        return (
            self.warrior_1.public_battle_results or
            self.warrior_2.public_battle_results
        )


# TODO: rename to Game, the "Rename" step of docs/game-migration.md
class DBGame(GoalRelatedMixin, models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    battle = models.ForeignKey(
        to='Battle',
        on_delete=models.CASCADE,
        related_name='games',
    )
    llm = models.CharField(
        max_length=20,
        choices=LLM.choices,
    )
    scheduled_at = models.DateTimeField(
        db_index=True,
        default=timezone.now,
    )
    # Warriors are in prompt order, unlike the battle's canonical order;
    # comparing warrior_1_id with battle.warrior_1_id recovers the direction,
    # so direction is derived, never stored (docs/game-migration.md).
    warrior_1 = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='+',
    )
    warrior_2 = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='+',
    )
    input_sha256 = models.BinaryField(
        max_length=32,
        null=True,
        blank=True,
    )
    text_unit = models.ForeignKey(
        to=TextUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    finish_reason = models.CharField(
        max_length=20,
        blank=True,
    )
    llm_version = models.CharField(
        max_length=100,
        blank=True,
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    attempts = models.PositiveSmallIntegerField(
        default=0,
    )

    class Meta:
        db_table = 'warriors_game'
        constraints = [
            models.UniqueConstraint(
                fields=('battle', 'warrior_1'),
                name='unique_battle_direction',
            ),
        ]

    @property
    def result(self):
        """What the LLM produced, empty until the game resolves."""
        if self.text_unit is None:
            return ''
        return self.text_unit.content

    def result_marked_for(self, warrior):
        """The result with the subsequence it shares with one warrior marked."""
        return lcs_mark(self.result, warrior.body)

    @cached_property
    def scores_list(self):
        return tuple(self.scores.all())

    def score_object(self, algorithm):
        """This game's score row under one algorithm, or None if unscored."""
        for score in self.scores_list:
            if score.algorithm == algorithm:
                return score
        return None


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
