"""
For warrior A that is near the top schedule such a battle that it is likely to lose.
"""

import numpy
from django.db.models import F

from .models import WarriorArena
from .rating import compute_omega_matrix


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
        ),
    ).order_by('-relative_rating')
    return qs
