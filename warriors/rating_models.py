import logging
import random

from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Abs

from .rating import GameScore, get_performance_rating


logger = logging.getLogger(__name__)
M_ELO_K = 1
MAX_ALLOWED_RATING_PER_GAME = 100


class RatingMixin(models.Model):
    class Meta:
        abstract = True
        indexes = [
            models.Index(
                fields=['arena', 'rating'],
                name='rating_index',
                condition=models.Q(moderation_passed=True),
            ),
            models.Index(
                Abs('rating_error'),
                name='rating_error_index',
            ),
        ]

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

    def update_rating(self):
        """
        Compute rating based on games played.

        We assume all battles form a tournament.
        """
        from .models import Battle, WarriorArena

        # collect relevant battles
        battles = {}  # opponent warrior id -> our BattleViewpoint
        for b in Battle.objects.with_warrior_arena(self).resolved().order_by('scheduled_at'):
            b = b.get_warrior_viewpoint(self)
            if b.score is None:
                continue
            battles[b.warrior_2_id] = b

        # collect scores
        scores = {}  # opponent warrior_arena id -> GameScore(score, opponent_rating, opponent_playstyle)
        warrior_arenas = {
            w.warrior_id: w
            for w in WarriorArena.objects.filter(
                arena_id=self.arena_id,
                warrior_id__in=battles.keys(),
            )
        }
        for b in battles.values():
            opponent = warrior_arenas[b.warrior_2_id]
            normalize_playstyle_len(opponent.rating_playstyle)
            scores[opponent.id] = GameScore(
                score=b.score,
                opponent_rating=opponent.rating,
                opponent_playstyle=opponent.rating_playstyle,
            )

        # find rating fitting our scores
        # we limit rating range for warriors with few games played
        max_allowed_rating = MAX_ALLOWED_RATING_PER_GAME * len(scores)
        normalize_playstyle_len(self.rating_playstyle)
        new_rating, new_playstyle, self.rating_fit_loss = get_performance_rating(
            list(scores.values()),
            allowed_rating_range=max_allowed_rating,
            k=M_ELO_K,
        )
        rating_error = new_rating - self.rating

        # update related warriors
        if rating_error and len(scores) > 0:
            error_per_opponent = rating_error / len(scores) / 2
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
                WarriorArena.objects.filter(id__in=ids_before).update(
                    rating=F('rating') - error_per_opponent,
                    rating_error=F('rating_error') + error_per_opponent,
                )
                WarriorArena.objects.filter(id=self.id).update(
                    rating=F('rating') + rating_error / 2,
                    rating_playstyle=new_playstyle,
                    rating_fit_loss=self.rating_fit_loss,
                    rating_error=0.0,
                )
                WarriorArena.objects.filter(id__in=ids_after).update(
                    rating=F('rating') - error_per_opponent,
                    rating_error=F('rating_error') + error_per_opponent,
                )

        return rating_error


def normalize_playstyle_len(playstyle):
    # Make sure playstyle vector is of fixed length.
    # This is used to automatically migrate data from different versions of M_ELO_K.
    # Also by default playstyle is initialized as empty array, so this functions as a default value.
    while len(playstyle) < M_ELO_K * 2:
        playstyle.append(random.random())
    while len(playstyle) > M_ELO_K * 2:
        playstyle.pop()
    assert len(playstyle) == M_ELO_K * 2


def update_rating(n=10):
    from .models import WarriorArena
    errors = []
    for _ in range(n):
        warrior = WarriorArena.objects.order_by(Abs('rating_error').desc()).first()
        if warrior is None:
            return
        error = warrior.update_rating()
        errors.append(error)
    max_error = max(abs(e) for e in errors) if errors else 0
    logger.info('Updated ratings. Max error: %s', max_error)
    return max_error
