from django.db import models
from django.utils.translation import gettext_lazy as _

from .score import ScoreAlgorithm


class Ranking(models.TextChoices):
    """
    The leaderboards, each reading the one battle stream through a score algorithm:
    a registry in code, not rows ("Rankings in code" in docs/data-model.md).
    """
    LCS = 'lcs', _('LCS ladder')
    SEMANTIC = 'semantic', _('Semantic ladder')

    @property
    def score_algorithm(self):
        return SCORE_ALGORITHMS[self]


SCORE_ALGORITHMS = {
    Ranking.LCS: ScoreAlgorithm.LCS,
    Ranking.SEMANTIC: ScoreAlgorithm.EMBEDDINGS,
}

# The ranking a page showing one opens on: the home page, `/leaderboard/`,
# and a warrior's page with no `?ranking=`.
# Presentation only; rating and matchmaking treat every ranking alike.
LEADING_RANKING = Ranking.LCS
