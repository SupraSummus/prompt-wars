import logging
import random
import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Abs
from django.utils import timezone

from .rankings import Ranking
from .rating import GameScore, get_performance_rating
from .warriors import Warrior


logger = logging.getLogger(__name__)
M_ELO_K = 1
MAX_ALLOWED_RATING_PER_GAME = 100
MAX_OLD_BATTLES = 100


class WarriorRatingQuerySet(models.QuerySet):
    def battleworthy(self):
        return self.filter(
            warrior__moderation_passed=True,
        )

    def ranked(self):
        """A leaderboard's order, best first."""
        return self.battleworthy().order_by('-rating')


class WarriorRating(models.Model):
    """One warrior's standing in one ranking (`Ranking`)."""
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    warrior = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='ratings',
        # `warrior_ranking_unique` leads with the warrior, so it serves as the index
        db_index=False,
    )
    ranking = models.CharField(
        max_length=20,
        choices=Ranking.choices,
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
    rating_error = models.FloatField(
        default=0.0,
    )
    rating_updated_at = models.DateTimeField(
        default=timezone.now,
    )
    # The opponents the last fit read: the ranked game count.
    # Matchmaking paces itself by the battle count instead (`create_battle`).
    games_played = models.PositiveIntegerField(
        default=0,
    )

    objects = WarriorRatingQuerySet.as_manager()

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=['warrior', 'ranking'],
                name='warrior_ranking_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=['ranking', 'rating'],
                name='ranking_rating_index',
            ),
            models.Index(
                Abs('rating_error'),
                name='warrior_rating_error_index',
            ),
        ]

    def __str__(self):
        return str(self.warrior)

    def get_absolute_url(self):
        return self.warrior.get_ranking_url(self.ranking)

    @property
    def rating_error_abs(self):
        return abs(self.rating_error)

    def update_rating(self):
        """
        Compute rating based on games played.

        We assume all battles form a tournament.
        """
        from .battles import MATCHMAKING_COOLDOWN, Battle

        now = timezone.now()
        algorithm = Ranking(self.ranking).score_algorithm

        # collect relevant battles
        old_battle_treshold = now - MATCHMAKING_COOLDOWN
        battles = {}  # opponent warrior id -> our score in that battle
        for b in Battle.objects.with_warrior(self.warrior_id).resolved().order_by(
            '-scheduled_at',
        ).prefetch_related(
            # a battle score is the mean over its games,
            # and a game's score rows hang off the game they name
            'games__scores',
        ):
            opponent_id = (
                b.warrior_2_id if b.warrior_1_id == self.warrior_id
                else b.warrior_1_id
            )
            if opponent_id in battles:
                continue  # we already have a more recent battle with this opponent
            # the display calls this same number, so the two cannot drift
            # ("A warrior's score is named once" in docs/battle-display.md)
            score = b.warrior_score(self.warrior_id, algorithm)
            if score is None:
                continue
            if b.scheduled_at < old_battle_treshold and len(battles) >= MAX_OLD_BATTLES:
                break  # all the remaining battles are old and we have enough to calculate rating
            battles[opponent_id] = score

        k = min(M_ELO_K, len(battles) // 2)

        # collect scores
        scores = {}  # opponent rating id -> GameScore(score, opponent_rating, opponent_playstyle)
        # a rated battle is fought by two warriors on the ladder (`enter_ladder`), so each has a rating
        opponent_ratings = ratings_by_warrior(self.ranking, battles.keys())
        for opponent_id, score in battles.items():
            opponent = opponent_ratings[opponent_id]
            normalize_playstyle_len(opponent.rating_playstyle, k)
            scores[opponent.id] = GameScore(
                score=score,
                opponent_rating=opponent.rating,
                opponent_playstyle=opponent.rating_playstyle,
            )

        # find rating fitting our scores
        # we limit rating range for warriors with few games played
        max_allowed_rating = MAX_ALLOWED_RATING_PER_GAME * len(scores)
        normalize_playstyle_len(self.rating_playstyle, k)
        new_rating, new_playstyle, self.rating_fit_loss = get_performance_rating(
            list(scores.values()),
            rating_guess=self.rating,
            playstyle_guess=self.rating_playstyle,
            allowed_rating_range=max_allowed_rating,
            k=k,
        )
        rating_error = new_rating - self.rating

        # update related warriors
        if scores:
            error_per_opponent = rating_error / len(scores) / 2
        else:
            error_per_opponent = 0
        ids_before = []
        ids_after = []
        for id_ in scores.keys():
            assert id_ != self.id
            if id_ < self.id:
                ids_before.append(id_)
            else:
                ids_after.append(id_)
        with transaction.atomic():
            # we need to do updates in a speicific order to avoid deadlocks
            WarriorRating.objects.filter(id__in=ids_before).update(
                rating=F('rating') - error_per_opponent,
                rating_error=F('rating_error') + error_per_opponent,
            )
            WarriorRating.objects.filter(id=self.id).update(
                rating=F('rating') + rating_error / 2,
                rating_playstyle=new_playstyle,
                rating_fit_loss=self.rating_fit_loss,
                rating_error=0.0,
                games_played=len(scores),
                rating_updated_at=now,
            )
            WarriorRating.objects.filter(id__in=ids_after).update(
                rating=F('rating') - error_per_opponent,
                rating_error=F('rating_error') + error_per_opponent,
            )

        return rating_error


def normalize_playstyle_len(playstyle, k=M_ELO_K):
    # Make sure playstyle vector is of fixed length.
    # This is used to automatically migrate data from different versions of M_ELO_K.
    # Also by default playstyle is initialized as empty array, so this functions as a default value.
    while len(playstyle) < k * 2:
        playstyle.append(random.uniform(
            -MAX_ALLOWED_RATING_PER_GAME ** 0.5,
            MAX_ALLOWED_RATING_PER_GAME ** 0.5,
        ))
    while len(playstyle) > k * 2:
        playstyle.pop()
    assert len(playstyle) == k * 2


def enter_ladder(warrior):
    """
    Put a warrior on the ladder: its clock starts, and it gets a rating in every ranking.

    The one place either happens ("One clock per warrior" in docs/data-model.md);
    entering again changes nothing.
    """
    with transaction.atomic():
        if warrior.next_battle_schedule is None:
            warrior.next_battle_schedule = timezone.now()
            warrior.save(update_fields=['next_battle_schedule'])
        WarriorRating.objects.bulk_create(
            [WarriorRating(warrior=warrior, ranking=ranking) for ranking in Ranking],
            ignore_conflicts=True,
        )


def ratings_by_warrior(ranking, warrior_ids):
    """The warriors' ratings in one ranking, a dict by warrior id; a warrior off the ladder has none."""
    return {
        rating.warrior_id: rating
        for rating in WarriorRating.objects.filter(
            ranking=ranking,
            warrior_id__in=warrior_ids,
        )
    }


def update_rating(n=1, now=None):
    errors = []
    for _ in range(n):
        warrior = WarriorRating.objects.order_by(Abs('rating_error').desc()).first()
        if warrior is None:
            return
        error = warrior.update_rating()
        errors.append(error)
    max_error = max(abs(e) for e in errors) if errors else 0
    logger.info('Updated ratings. Max error: %s', max_error)
    return max_error
