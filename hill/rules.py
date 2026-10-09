"""
The game rules of King of the Hill: constants, eligibility and standings.

`Hill` holds the owner's switches: on or off, the model, the daily spend cap and the queue.
Everything else is a game rule, a constant here that changes only with a code review.
Why the game is shaped this way, and what was rejected: docs/king-of-the-hill.md.
"""
import dataclasses
import datetime
from collections import Counter

from warriors.lcs import lcs_len
from warriors.warriors import Warrior

from .models import CrownBlock, HillAttempt, Round


# The UTC hour of the daily boundary between rounds.
HILL_HANDOVER_HOUR = 17
# Attacks per player per round; voided ones are refunded.
HILL_ATTEMPTS_PER_PLAYER = 5
# The battle score that takes the hill: a bare half flips on noise.
HILL_WIN_SCORE = 0.55
# Rounds a boss holds unbeaten before the hill passes on anyway.
HILL_MAX_REIGN_ROUNDS = 3

# A boss's text, and variants of it, can't return for this many rounds,
# so a dethroned spell's family can't alternate with its conqueror.
HILL_NO_RETURN_ROUNDS = 7

# How long the handover waits for attacks still being judged at the cutoff before marking them late.
HILL_HANDOVER_GRACE = datetime.timedelta(minutes=10)
# No round is shorter, so a restart or a forced crown near the boundary can't make a round of minutes.
HILL_MIN_ROUND = datetime.timedelta(hours=12)

# Crown gates (`crown_block`), against bosses whose battles force a degenerate reply.
# Characters of the attacker that must survive, summed over both games: a glyph echo wins on almost nothing.
HILL_MIN_SURVIVED_CHARS = 50
# Distinct character bigrams each reply needs: floods and fixed verdicts have few.
HILL_MIN_REPLY_BIGRAMS = 20

# An attack pending this long is shown as slow: several times the minute a battle normally takes,
# so the notice means a backed-up queue or a retry, not an ordinary wait.
HILL_DELAYED_AFTER = datetime.timedelta(minutes=5)

# The order that crowns, and that ranks the standings.
# On an equal score, more surviving text is the stronger hold;
# on a full tie, the earlier attack found it first.
CROWN_ORDER = ('-score', '-survived_chars', 'created_at')


def best_eligible(attempts):
    return attempts.eligible().order_by(*CROWN_ORDER).first()


def beats_boss(attempt):
    """
    Whether a counted attempt takes the hill if nobody does better:
    `HillAttemptQuerySet.eligible`, for one row, past the margin.
    """
    return (
        attempt.crown_block == CrownBlock.NONE and
        attempt.score >= HILL_WIN_SCORE and
        attempt.warrior.moderation_passed is True
    )


def survived_chars(body, results):
    """Characters of a spell that survived, in order, summed over its games' results."""
    return sum(lcs_len(body, result) for result in results)


def _distinct_bigrams(text):
    return len({text[i:i + 2] for i in range(len(text) - 1)})


def crown_block(survived, results):
    """
    Why a scored attempt can't take the hill, or '' if it can.

    These gates stop a boss that forces a degenerate reply —
    a lone glyph, a flood, a fixed verdict —
    from being beaten, or held, by attacks that fit the same degenerate reply.
    """
    if survived < HILL_MIN_SURVIVED_CHARS:
        return CrownBlock.TOO_LITTLE_SURVIVED
    if any(_distinct_bigrams(result) < HILL_MIN_REPLY_BIGRAMS for result in results):
        return CrownBlock.REPETITIVE_REPLY
    return CrownBlock.NONE


def recent_bosses(hill_round):
    """The round's boss and every boss of the `HILL_NO_RETURN_ROUNDS` rounds before it."""
    return Warrior.objects.filter(
        id__in=Round.objects.filter(
            hill_id=hill_round.hill_id,
            number__gte=hill_round.number - HILL_NO_RETURN_ROUNDS,
            number__lte=hill_round.number,
        ).values('boss_id'),
    )


def budget_used(hill_round):
    """Attacks charged to a round's budget (`Hill.daily_attempt_limit`): every one has a battle to pay for."""
    return hill_round.attempts.count()


@dataclasses.dataclass(frozen=True)
class Standing:
    """One row of a round's standings: an attacker's best attempt."""
    rank: int
    attempt: HillAttempt
    # k in "Attacker #k": the order of the attacker's first live attempt in the round
    attacker_number: int
    # the attacker's attempts in the round, as the per-player cap counts them
    attempt_count: int


def standings(hill_round):
    """
    The round's attackers, each by their best counted attempt.

    One row per identity, so one player's variants can't fill the table;
    eligible attempts rank before crown-blocked ones,
    so a degenerate echo with a high score never sits at the top.
    """
    best = list(
        hill_round.attempts.counted().select_related(
            'warrior',
        ).defer(
            'warrior__voyage_3_embedding',
        ).order_by(
            # '' sorts first: an identity's best eligible attempt, if it has one
            'identity', 'crown_block', *CROWN_ORDER,
        ).distinct('identity'),
    )
    best.sort(key=lambda attempt: (
        attempt.crown_block != CrownBlock.NONE,
        -attempt.score,
        -attempt.survived_chars,
        attempt.created_at,
    ))
    attacker_numbers = {}
    attempt_counts = Counter()
    for identity in hill_round.attempts.live().order_by('created_at').values_list('identity', flat=True):
        attacker_numbers.setdefault(identity, len(attacker_numbers) + 1)
        attempt_counts[identity] += 1
    return [
        Standing(
            rank=rank,
            attempt=attempt,
            attacker_number=attacker_numbers[attempt.identity],
            attempt_count=attempt_counts[attempt.identity],
        )
        for rank, attempt in enumerate(best, 1)
    ]


def standings_stats(rows):
    """
    A round's numbers, from its standings `rows`: its attackers, how many beat the boss,
    and the boss's mean share against each one's best (None with no attackers).
    """
    return {
        'attackers': len(rows),
        'broke_through': sum(beats_boss(row.attempt) for row in rows),
        'boss_held': sum(1 - row.attempt.score for row in rows) / len(rows) if rows else None,
    }


def crowned_round(attempt):
    """The first round `attempt`'s spell held the hill in, or None if it never took it."""
    return Round.objects.filter(boss_attempt=attempt).select_related('boss').order_by('number').first()


def is_public(attempt):
    """
    Whether anyone may see `attempt`, not only its author: once it has taken the hill.

    Publishing a boss is all the attack form's consent covers,
    so nothing else an attacker sends is shown to anyone else, ever.
    A spell flagged since, by moderation or the owner's takedown, is taken back.
    """
    return (
        attempt.warrior.moderation_passed is True and
        Round.objects.filter(boss_attempt=attempt).exists()
    )


def replies_public(attempt):
    """
    Whether a public attempt's battle replies may be shown to anyone but its author.

    Only once moderation passed them (`hill.tasks.moderate_crowned_attempt`),
    and not once the boss it fought is flagged: the replies echo that boss's text.
    """
    return (
        attempt.output_moderation_passed is True and
        attempt.hill_round.boss_shown
    )
