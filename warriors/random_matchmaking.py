import datetime
import random

from django.db import transaction
from django.utils import timezone

from .battles import Battle
from .models import WarriorArena


MATCHMAKING_MAX_RATING_DIFF = 100  # rating diff of 100 means expected score is 64%


def schedule_battles(n=10, now=None):
    for _ in range(n):
        schedule_battle(now=now)


@transaction.atomic
def schedule_battle(now=None):
    if now is None:
        now = timezone.now()
    warrior = WarriorArena.objects.battleworthy().filter(
        next_battle_schedule__lte=now,
    ).order_by('next_battle_schedule').select_for_update(
        no_key=True,
        skip_locked=True,
    ).first()
    if warrior is None:
        return
    if (
        not warrior.arena.enabled or
        (opponent := find_opponent(warrior)) is None
    ):
        warrior.next_battle_schedule = now + get_next_battle_delay(warrior) + datetime.timedelta(minutes=1)
        warrior.save(update_fields=['next_battle_schedule'])
        return
    create_battle(warrior, opponent, now=now)


def create_battle(warrior, opponent, now=None):
    """
    Returns:
        Battle: The created battle instance
    """
    if now is None:
        now = timezone.now()

    battle = Battle.create_from_warriors(warrior, opponent)

    # Update warrior1 statistics
    warrior.games_played = Battle.objects.with_warrior_arena(warrior).count()
    warrior.next_battle_schedule = now + get_next_battle_delay(warrior)
    warrior.save(update_fields=[
        'games_played',
        'next_battle_schedule',
    ])

    # Update warrior2 statistics
    opponent.games_played = Battle.objects.with_warrior_arena(opponent).count()
    opponent.save(update_fields=['games_played'])

    # Generate voyage 3 embeddings in case not already generated.
    # Normally we generate them when warrior is created.
    # This is for old warriors created before we introduced embeddings.
    # Possibly this can be removed in the future.
    warrior.warrior.schedule_voyage_3_embedding()
    opponent.warrior.schedule_voyage_3_embedding()

    return battle


def find_opponent(warrior_arena, max_rating_diff=MATCHMAKING_MAX_RATING_DIFF):
    """
    Find a suitable opponent for the given warrior arena.

    Args:
        warrior_arena (WarriorArena): The warrior arena to find an opponent for
        max_rating_diff (int): Maximum rating difference between opponents

    Returns:
        WarriorArena: A suitable opponent, or None if none found
    """
    return find_opponents(
        warrior_arena, max_rating_diff
    ).order_by('?').select_for_update(
        no_key=True,
        skip_locked=True,
    ).first()


def find_opponents(warrior_arena, max_rating_diff=MATCHMAKING_MAX_RATING_DIFF):
    """
    Find suitable opponents for the given warrior arena.

    Args:
        warrior_arena (WarriorArena): The warrior arena to find opponents for
        max_rating_diff (int): Maximum rating difference between opponents

    Returns:
        QuerySet: A queryset of suitable opponents
    """
    battle_worthy_qs = WarriorArena.objects.battleworthy()
    top_rating = warrior_arena.rating + max_rating_diff
    bottom_rating = warrior_arena.rating - max_rating_diff

    historic_battles = Battle.objects.with_warrior_arena(warrior_arena).recent()

    return battle_worthy_qs.filter(
        arena_id=warrior_arena.arena_id,
        rating__lt=top_rating,
        rating__gt=bottom_rating,
    ).exclude(
        id=warrior_arena.id,
    ).exclude(
        warrior_id__in=historic_battles.values('warrior_1'),
    ).exclude(
        warrior_id__in=historic_battles.values('warrior_2'),
    )


def get_next_battle_delay(warrior_arena):
    """
    Get delay to the game N+1, where N is the number of games with this warrior.
    Games are exponentially less and less frequent.
    """
    K = 2
    time_unit = datetime.timedelta(minutes=1)
    exponent = warrior_arena.games_played - random.random()
    if exponent > 25:
        # avoid overflow
        exponent = 25
    return max(
        K ** exponent - 1,
        0,
    ) * time_unit
