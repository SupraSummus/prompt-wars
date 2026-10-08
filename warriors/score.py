import uuid

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
    One game's score under one scoring algorithm.

    Similarities are stored in game order,
    the order a reader of the game sees its warriors in,
    so the scoring properties read straight off the row
    with nothing rewriting them on the way out.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    game = models.ForeignKey(
        to='Game',
        on_delete=models.CASCADE,
        related_name='scores',
        # unique_game_algorithm leads with game,
        # so its index answers every lookup by game a plain one would.
        db_index=False,
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
        constraints = [
            models.UniqueConstraint(
                fields=('game', 'algorithm'),
                name='unique_game_algorithm',
            ),
        ]

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

    def score_for(self, warrior_id):
        """
        This score from one named warrior's side.

        The row's fields are in game order and it names its game,
        so a warrior's number is a choice between the two of them
        rather than a rewrite
        ("A warrior's score is named once" in docs/battle-display.md).
        """
        if warrior_id == self.game.warrior_1_id:
            return self.score
        assert warrior_id == self.game.warrior_2_id
        return self.score_rev

    def similarity_for(self, warrior_id):
        """How much of one named warrior's prompt survived into the result."""
        if warrior_id == self.game.warrior_1_id:
            return self.warrior_1_similarity
        assert warrior_id == self.game.warrior_2_id
        return self.warrior_2_similarity

    @property
    def cooperation_score(self):
        """
        Fusion quality, as opposed to who won:
        high when both prompts survive into the output in balance
        (the smaller-to-larger similarity ratio)
        and are distinct to begin with —
        the ``1 - warriors_similarity`` factor zeroes out mutual copying,
        where balanced survival would be trivial.
        For why this axis matters, see "The central tension"
        in docs/design-tensions.md.
        """
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


def get_or_create_game_score(game, algorithm):
    """
    The score of one game under one algorithm.

    Keyed on (game, algorithm), the uniqueness the schema guards,
    so a racing second call loses its insert and reads the row instead.
    """
    game_score, _ = GameScore.objects.get_or_create(
        game=game,
        algorithm=algorithm,
        defaults={
            # a callable, so a hit leaves no orphan goal behind
            'processed_goal': lambda: schedule(ensure_score),
        },
    )
    return game_score


def ensure_score(goal):
    game_score = GameScore.objects.get(processed_goal=goal)
    return _ensure_score(game_score)


def _ensure_score(game_score, save=True):
    game = game_score.game

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
