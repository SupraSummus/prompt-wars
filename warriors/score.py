import uuid
from dataclasses import dataclass

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_goals.models import AllDone, RetryMeLater, schedule
from django_goals.utils import GoalRelatedMixin, is_goal_completed

from .lcs import lcs_len


class ScoreAlgorithm(models.TextChoices):
    LCS = 'lcs', _('Longest Common Subsequence')
    EMBEDDINGS = 'embeddings', _('Embeddings')


class GameScore(GoalRelatedMixin, models.Model):
    """
    Stores the score for a single game (battle direction) and scoring algorithm.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    battle = models.ForeignKey(
        to='Battle',
        on_delete=models.CASCADE,
        related_name='game_scores',
    )
    direction = models.CharField(
        max_length=3,
        choices=[
            ('1_2', _('1→2')),
            ('2_1', _('2→1')),
        ],
    )
    algorithm = models.CharField(
        max_length=20,
        choices=ScoreAlgorithm.choices,
    )
    warrior_1_similarity = models.FloatField(
        null=True,
        blank=True,
        help_text=_('Similarity score between result and warrior 1, in game order.'),
    )
    warrior_2_similarity = models.FloatField(
        null=True,
        blank=True,
        help_text=_('Similarity score between result and warrior 2, in game order.'),
    )
    warriors_similarity = models.FloatField(
        null=True,
        blank=True,
        help_text=_('Similarity score between warriors'),
    )

    class Meta:
        unique_together = [
            ('battle', 'direction', 'algorithm'),
        ]
        indexes = [
            models.Index(fields=['battle', 'direction', 'algorithm']),
        ]


def get_or_create_game_score(battle, direction, algorithm):
    game_score = GameScore.objects.filter(
        battle=battle,
        direction=direction,
        algorithm=algorithm,
    ).first()
    if game_score is None:
        game_score = GameScore.objects.create(
            battle=battle,
            direction=direction,
            algorithm=algorithm,
            processed_goal=schedule(ensure_score),
        )
    return game_score


def ensure_score(goal):
    game_score = GameScore.objects.get(processed_goal=goal)
    return _ensure_score(game_score)


def _ensure_score(game_score, save=True):
    from .battles import Game
    game = Game(game_score.battle, game_score.direction)

    if game.finish_reason == 'error':
        _set_similarity(game_score, None, None, None, save=save)
        return AllDone()

    if game_score.algorithm == ScoreAlgorithm.LCS:
        return ensure_lcs_score(game_score, game, save=save)
    elif game_score.algorithm == ScoreAlgorithm.EMBEDDINGS:
        return ensure_embeddings_score(game_score, game, save=save)
    else:
        raise ValueError(f'Unknown algorithm: {game_score.algorithm}')


def ensure_lcs_score(game_score, game, save=True):
    _set_similarity(
        game_score,
        _lcs_similarity(game.warrior_1.body, game.result),
        _lcs_similarity(game.warrior_2.body, game.result),
        warriors_similarity=_lcs_similarity(
            game.warrior_1.body,
            game.warrior_2.body,
        ),
        save=save,
    )
    return AllDone()


def _lcs_similarity(warrior, result):
    if result is None:
        return None
    return lcs_len(warrior, result) / max(len(warrior), len(result))


def ensure_embeddings_score(game_score, game, save=True):
    if not is_goal_completed(game.text_unit.voyage_3_embedding_goal):
        return RetryMeLater(
            message='Need to wait for result text embedding',
            precondition_goals=[game.text_unit.voyage_3_embedding_goal],
        )

    if not is_goal_completed(game.warrior_1.voyage_3_embedding_goal):
        return RetryMeLater(
            message='Need to wait for warrior 1 embedding',
            precondition_goals=[game.warrior_1.voyage_3_embedding_goal],
        )

    if not is_goal_completed(game.warrior_2.voyage_3_embedding_goal):
        return RetryMeLater(
            message='Need to wait for warrior 2 embedding',
            precondition_goals=[game.warrior_2.voyage_3_embedding_goal],
        )

    _set_similarity(
        game_score,
        _warrior_similarity(game.text_unit, game.warrior_1),
        _warrior_similarity(game.text_unit, game.warrior_2),
        warriors_similarity=_warrior_similarity(game.warrior_1, game.warrior_2),
        save=save,
    )
    return AllDone()


def _warrior_similarity(text_unit, warrior):
    if (
        not text_unit or
        not text_unit.voyage_3_embedding or
        not warrior.voyage_3_embedding
    ):
        return None
    a = text_unit.voyage_3_embedding
    b = warrior.voyage_3_embedding
    assert len(a) == len(b)
    return sum(aa * bb for aa, bb in zip(a, b))


def _set_similarity(
    game_score,
    warrior_1_similarity, warrior_2_similarity,
    warriors_similarity,
    save=True,
):
    game_score.warrior_1_similarity = warrior_1_similarity
    game_score.warrior_2_similarity = warrior_2_similarity
    game_score.warriors_similarity = warriors_similarity
    if save:
        game_score.save(update_fields=[
            'warrior_1_similarity',
            'warrior_2_similarity',
            'warriors_similarity',
        ])


@dataclass(frozen=True)
class GameScoreViewpoint:
    game_score: GameScore
    viewpoint: str  # 1 is normal, 2 is reversed

    def __getattr__(self, key):
        if key in (
            'direction',
            'algorithm',
        ):
            return getattr(self.game_score, key)

        w1, w2 = ('1', '2') if self.viewpoint == '1' else ('2', '1')
        if key == 'warrior_1_similarity':
            return getattr(self.game_score, f'warrior_{w1}_similarity')
        if key == 'warrior_2_similarity':
            return getattr(self.game_score, f'warrior_{w2}_similarity')
        if key == 'warriors_similarity':
            return self.game_score.warriors_similarity

        return super().__getattribute__(key)

    @property
    def score(self):
        """
        Score of warrior 1.
        Score of warrior 2 is `1 - score`.
        """
        if self.warrior_1_similarity is None or self.warrior_2_similarity is None:
            return None

        if self.algorithm == ScoreAlgorithm.LCS:
            if self.warrior_1_similarity + self.warrior_2_similarity == 0:
                return 0.5
            return self.warrior_1_similarity / (self.warrior_1_similarity + self.warrior_2_similarity)

        if self.algorithm == ScoreAlgorithm.EMBEDDINGS:
            if self.warrior_1_similarity > self.warrior_2_similarity:
                return 1.0
            elif self.warrior_1_similarity < self.warrior_2_similarity:
                return 0.0
            else:
                return 0.5

    @property
    def score_rev(self):
        """
        Score of warrior 2.
        """
        s = self.score
        if s is None:
            return None
        return 1.0 - s

    @property
    def cooperation_score(self):
        if (
            self.warriors_similarity is None or
            self.warrior_1_similarity is None or
            self.warrior_2_similarity is None
        ):
            return None
        smaller_similarity, larger_similarity = sorted([
            self.warrior_1_similarity,
            self.warrior_2_similarity,
        ])
        if larger_similarity <= 0:
            return 0
        return (
            smaller_similarity / larger_similarity
        ) * (1 - self.warriors_similarity)
