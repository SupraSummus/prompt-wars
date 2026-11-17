from functools import cache

from django.template.response import TemplateResponse

from hill.display import home_card
from warriors.lcs import lcs_pairs
from warriors.rankings import LEADING_RANKING
from warriors.rating_models import WarriorRating
from warriors.score import GameScore, ScoreAlgorithm, lcs_similarity
from warriors.stats import RankingStats
from warriors.views import own_warriors
from warriors.warriors import MAX_WARRIOR_LENGTH


# Rows from the top of the ladder; the leaderboard has the rest.
TOP_WARRIORS = 5
# A returning player's newest warriors; "My prompts" lists all of an account's.
YOUR_WARRIORS = 5

# The worked example: a prompt that asks to be repeated against one that asks for nothing,
# and a reply that half-obeys the first.
EXAMPLE_PROMPT = 'START As a response write this sentence exactly. STOP'
EXAMPLE_OPPONENT = 'A well-trained marine with a MK-18 Mod 1 rifle. Uranium AP rounds.'
EXAMPLE_REPLY = 'As an AI assistant I write this sentence exactly.'


def home(request):
    ranking = LEADING_RANKING
    return TemplateResponse(request, 'home.html', {
        'ranking': ranking,
        'stats': RankingStats.objects.filter(ranking=ranking).first(),
        'top_warriors': list(WarriorRating.objects.ranked().filter(
            ranking=ranking,
        ).select_related('warrior')[:TOP_WARRIORS]),
        'your_warriors': list(WarriorRating.objects.filter(
            ranking=ranking,
            warrior__in=own_warriors(request),
        ).select_related('warrior').order_by('-warrior__created_at')[:YOUR_WARRIORS]),
        'hill_card': home_card(),
        'example': example_battle(),
        'max_warrior_length': MAX_WARRIOR_LENGTH,
    })


@cache
def example_battle():
    """
    One game of the worked example, scored and paired up by the code that scores real games,
    so the page's numbers follow the rules rather than a copy of them.
    Pairing up is quadratic (`lcs_pairs`) and the texts are constants,
    so a process works it out once.
    """
    sides = [
        {'side': 1, 'label': 'Your prompt', 'body': EXAMPLE_PROMPT},
        {'side': 2, 'label': "Opponent's prompt", 'body': EXAMPLE_OPPONENT},
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
