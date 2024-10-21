"""
For warrior A that is near the top, schedule such a battle that it is likely to lose.
"""

import logging

import numpy
from django.db.models import F

from .models import Arena, Battle, WarriorArena
from .rating import compute_omega_matrix


logger = logging.getLogger(__name__)


def schedule_losing_battle_top():
    for arena in Arena.objects.all():
        battle = schedule_losing_battle_arena(arena)
        logger.info('Scheduled battle %s', battle)


def schedule_losing_battle_arena(arena):
    rating = 4000  # arbitrary value, higer than any real rating
    while True:
        warrior_arena = WarriorArena.objects.filter(
            arena=arena,
            rating__lt=rating,
        ).battleworthy().order_by('-rating').first()
        if warrior_arena is None:
            return None
        rating = warrior_arena.rating
        battle = schedule_losing_battle(warrior_arena)
        if battle:
            return battle


def schedule_losing_battle(warrior_arena):
    for opponent in get_strongest_opponents(warrior_arena).filter(
        rating__lt=warrior_arena.rating,
        relative_rating__gte=0,
    )[:20]:
        has_recent_battle = Battle.objects.with_warriors(warrior_arena, opponent).recent().exists()
        if has_recent_battle:
            continue
        return warrior_arena.create_battle(opponent)


def get_strongest_opponents(warrior_arena):
    assert len(warrior_arena.rating_playstyle) == 2
    omega = compute_omega_matrix(k=1)  # it should be 2x2 matrix
    our_playstyle = numpy.array(warrior_arena.rating_playstyle)
    rating_correction = our_playstyle @ omega
    qs = WarriorArena.objects.battleworthy().filter(
        arena_id=warrior_arena.arena_id,
    ).exclude(
        id=warrior_arena.id,
    ).annotate(
        relative_rating=F('rating') - (
            F('rating_playstyle__0') * rating_correction[0] +
            F('rating_playstyle__1') * rating_correction[1]
        ) - warrior_arena.rating
    ).order_by('-relative_rating')
    return qs
