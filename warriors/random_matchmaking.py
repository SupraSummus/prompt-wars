import datetime
import random

from django.db import transaction
from django.utils import timezone

from .battles import Battle
from .rankings import Ranking
from .rating_models import WarriorRating
from .warriors import Warrior


MATCHMAKING_MAX_RATING_DIFF = 100  # rating diff of 100 means expected score is 64%


def schedule_battles(n=10, now=None):
    for _ in range(n):
        schedule_battle(now=now)


@transaction.atomic
def schedule_battle(now=None, ranking=None):
    """
    A battle for the warrior whose turn is due,
    against one near it in a ranking drawn at random unless given.
    """
    if now is None:
        now = timezone.now()
    if ranking is None:
        ranking = random.choice(list(Ranking))
    warrior = Warrior.objects.on_ladder().filter(
        next_battle_schedule__lte=now,
    ).order_by('next_battle_schedule').select_for_update(
        no_key=True,
        skip_locked=True,
    ).first()
    if warrior is None:
        return
    opponent = find_opponent(warrior, ranking)
    if opponent is None:
        warrior.next_battle_schedule = (
            now + get_next_battle_delay(battle_count(warrior)) + datetime.timedelta(minutes=1)
        )
        warrior.save(update_fields=['next_battle_schedule'])
        return
    create_battle(warrior, opponent, now=now)


def create_battle(warrior, opponent, now=None):
    """
    A ladder battle, and the next one for `warrior` scheduled by its battle count.

    The opponent's clock is left alone:
    being picked does not spend its own turn.
    """
    if now is None:
        now = timezone.now()

    battle = Battle.create_from_warriors(warrior, opponent)

    warrior.next_battle_schedule = now + get_next_battle_delay(battle_count(warrior))
    warrior.save(update_fields=['next_battle_schedule'])

    # Generate voyage 3 embeddings in case not already generated.
    # Normally we generate them when warrior is created.
    # This is for old warriors created before we introduced embeddings.
    # Possibly this can be removed in the future.
    warrior.schedule_voyage_3_embedding()
    opponent.schedule_voyage_3_embedding()

    return battle


def battle_count(warrior):
    return Battle.objects.with_warrior(warrior.id).count()


def find_opponent(warrior, ranking, max_rating_diff=MATCHMAKING_MAX_RATING_DIFF):
    """A random suitable opponent for the warrior (`find_opponents`), or None."""
    return find_opponents(warrior, ranking, max_rating_diff).order_by('?').first()


def find_opponents(warrior, ranking, max_rating_diff=MATCHMAKING_MAX_RATING_DIFF):
    """
    The warriors near this one's rating in `ranking`
    that it has not fought within the cooldown.
    """
    rating = WarriorRating.objects.get(warrior=warrior, ranking=ranking)
    historic_battles = Battle.objects.with_warrior(warrior.id).recent()
    return Warrior.objects.on_ladder().filter(
        ratings__ranking=ranking,
        ratings__rating__lt=rating.rating + max_rating_diff,
        ratings__rating__gt=rating.rating - max_rating_diff,
    ).exclude(
        id=warrior.id,
    ).exclude(
        id__in=historic_battles.values('warrior_1'),
    ).exclude(
        id__in=historic_battles.values('warrior_2'),
    )


def get_next_battle_delay(battle_count):
    """
    Get delay to the battle N+1, where N is the number of ladder battles the warrior fought.
    Games are exponentially less and less frequent.

    The front-loaded start is deliberate:
    a fresh warrior fights within minutes,
    and that instant feedback is what makes drive-by creation work
    (see "keep the fast lane" in docs/rounds.md
    before slowing this down).
    """
    K = 2
    time_unit = datetime.timedelta(minutes=1)
    exponent = battle_count - random.random()
    if exponent > 25:
        # avoid overflow
        exponent = 25
    return max(
        K ** exponent - 1,
        0,
    ) * time_unit
