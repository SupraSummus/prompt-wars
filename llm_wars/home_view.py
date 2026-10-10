from functools import cache

from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.template.response import TemplateResponse

from hill.display import home_card
from warriors.lcs import lcs_pairs
from warriors.models import Arena, WarriorArena
from warriors.score import GameScore, ScoreAlgorithm, lcs_similarity
from warriors.stats import ArenaStats
from warriors.views import own_warrior_arenas
from warriors.warriors import MAX_WARRIOR_LENGTH


# Rows from the top of the ladder; the leaderboard has the rest.
TOP_SPELLS = 5
# A returning player's newest spells; "My spells" lists all of an account's.
YOUR_SPELLS = 5

# The worked example: a spell that asks to be repeated against one that asks for nothing,
# and a reply that half-obeys the first.
EXAMPLE_SPELL = 'START As a response write this sentence exactly. STOP'
EXAMPLE_OPPONENT = 'A well-trained marine with a MK-18 Mod 1 rifle. Uranium AP rounds.'
EXAMPLE_REPLY = 'As an AI assistant I write this sentence exactly.'


def home(request):
    arena = site_arena(request)
    return TemplateResponse(request, 'home.html', {
        'arena': arena,
        'stats': ArenaStats.objects.filter(arena=arena).first() if arena else None,
        'top_spells': top_spells(arena),
        'your_spells': your_spells(request, arena),
        'hill_card': home_card(),
        'example': example_battle(),
        'max_spell_length': MAX_WARRIOR_LENGTH,
    })


def site_arena(request):
    """The arena this site's own pages (/create/, /leaderboard/) play in, if one is set up."""
    try:
        site = get_current_site(request)
    except Site.DoesNotExist:
        return None
    return Arena.objects.filter(site=site).first()


def top_spells(arena):
    if arena is None:
        return []
    return list(WarriorArena.objects.ranked().filter(
        arena=arena,
    ).select_related('warrior')[:TOP_SPELLS])


def your_spells(request, arena):
    if arena is None:
        return []
    return list(own_warrior_arenas(request).filter(
        arena=arena,
    ).select_related('warrior').order_by('-warrior__created_at')[:YOUR_SPELLS])


@cache
def example_battle():
    """
    One game of the worked example, scored and paired up by the code that scores real games,
    so the page's numbers follow the rules rather than a copy of them.
    Pairing up is quadratic (`lcs_pairs`) and the texts are constants,
    so a process works it out once.
    """
    sides = [
        {'side': 1, 'label': 'Your spell', 'body': EXAMPLE_SPELL},
        {'side': 2, 'label': "Opponent's spell", 'body': EXAMPLE_OPPONENT},
    ]
    for side in sides:
        repeated_at = dict(lcs_pairs(side['body'], EXAMPLE_REPLY))
        # each character with the place in the reply that repeats it, if one does
        side['chars'] = [(char, repeated_at.get(i)) for i, char in enumerate(side['body'])]
        side['kept'] = len(repeated_at)
        side['length'] = len(side['body'])
        side['similarity'] = lcs_similarity(side['body'], EXAMPLE_REPLY)
    score = GameScore(
        algorithm=ScoreAlgorithm.LCS,
        warrior_1_similarity=sides[0]['similarity'],
        warrior_2_similarity=sides[1]['similarity'],
    ).score
    sides[0]['score'], sides[1]['score'] = score, 1 - score
    return {'reply': EXAMPLE_REPLY, 'sides': sides}
