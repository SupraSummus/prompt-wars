"""
Where an attack stands, read from the rows its battle leaves behind.

The battle's goals never report back to the hill;
the status poll, the sweep and the handover each read the battle,
and whichever sees an outcome first stores it (`finalize_attempt`).
"""
import logging

from django.db import transaction
from django.db.models import Prefetch, Q

from warriors.score import ScoreAlgorithm
from warriors.tasks import MAX_TRANSIENT_RETRIES
from warriors.text_unit import TextUnit

from .models import AttemptState, HillAttempt
from .rules import HILL_DELAYED_AFTER, crown_block, survived_chars


logger = logging.getLogger(__name__)


def with_status_data(attempts):
    """
    `attempts` with every row `attempt_status` and `finalize_attempt` read, fetched up front.

    The embedding vectors of the prompt and the replies are left behind:
    the hill never reads them, and the status poll runs this every few seconds.
    """
    return attempts.select_related(
        'warrior',
        'battle',
    ).defer(
        # select_related doesn't apply `WarriorManager`'s defer
        'warrior__voyage_3_embedding',
    ).prefetch_related(
        Prefetch('battle__games__text_unit', queryset=TextUnit.objects.defer('voyage_3_embedding')),
        'battle__games__processed_goal',
        'battle__games__scores__processed_goal',
    )


def _is_scored(game):
    score = game.score_object(ScoreAlgorithm.LCS)
    return (
        score is not None and
        score.warrior_1_similarity is not None and
        score.warrior_2_similarity is not None
    )


def _ran_out_of_retries(game):
    """Resolved as an error after its last transient retry: as far as anyone can tell, an outage."""
    return (
        game.resolved_at is not None and
        game.finish_reason == 'error' and
        game.attempts > MAX_TRANSIENT_RETRIES
    )


def _content_failure(game):
    """Resolved with nothing usable: no candidate, reasoning that ate the token cap, a block or an empty stop."""
    return (
        game.resolved_at is not None and
        not _ran_out_of_retries(game) and
        (game.finish_reason == 'error' or not game.result)
    )


def _lost(game):
    """A game that can no longer get its LCS score."""
    score = game.score_object(ScoreAlgorithm.LCS)
    if game.is_error and (game.resolved_at is None or score is None):
        return True
    return score is not None and score.is_error and not _is_scored(game)


def attempt_status(attempt):
    """
    The state a pending attempt has reached, from durable rows only.

    Pass attempts through `with_status_data`.
    A content failure counts against the player, since at temperature 0 it mostly repeats;
    an infrastructure loss (retries run out, a goal given up) is void and refunded.
    Two orderings matter:
    an empty reply is a failure before it is a score,
    because LCS would score it an even split;
    and scored comes before any goal state,
    because a resolve goal can give up after its game scored,
    waiting on Voyage embeddings the hill never reads.
    """
    if attempt.state != AttemptState.PENDING:
        return attempt.state
    if attempt.warrior.moderation_passed is False:
        return AttemptState.FLAGGED
    games = attempt.battle.games_list
    if any(_content_failure(game) for game in games):
        return AttemptState.FAILED
    if any(_ran_out_of_retries(game) for game in games):
        return AttemptState.VOID
    if games and all(_is_scored(game) for game in games):
        return AttemptState.SCORED
    if any(_lost(game) for game in games):
        return AttemptState.VOID
    return AttemptState.PENDING


def stage_key(attempt, status, now):
    """
    A short key for the status line an attempt's page shows.

    It changes exactly when the line must,
    so a poll can answer "nothing new" by comparing keys.
    A pending attempt is slow once it is older than `HILL_DELAYED_AFTER`
    or a game is retrying after a provider error.
    """
    if status != AttemptState.PENDING:
        return status
    slow = now - attempt.created_at > HILL_DELAYED_AFTER or any(
        game.resolved_at is None and game.attempts > 0
        for game in attempt.battle.games_list
    )
    return 'pending+slow' if slow else 'pending'


def finalize_attempt(attempt, status):
    """
    Store a terminal `status` on a pending attempt; True if this call stored it.

    A conditional update on the pending state:
    the status poll, the sweep and the handover may race,
    every one computes the same values, and the first one wins.
    A scored attempt gets its score, the characters that survived and its crown gate.
    `late` is left alone: a late attempt still gets a score, for its author.
    """
    if status == AttemptState.PENDING:
        return False
    fields = {'state': status}
    if status == AttemptState.SCORED:
        results = [game.result for game in attempt.battle.games_list]
        survived = survived_chars(attempt.warrior.body, results)
        fields.update(
            score=attempt.battle.warrior_score(attempt.warrior_id, ScoreAlgorithm.LCS),
            survived_chars=survived,
            crown_block=crown_block(survived, results),
        )
    updated = HillAttempt.objects.filter(
        id=attempt.id,
        state=AttemptState.PENDING,
    ).update(**fields)
    if updated:
        for name, value in fields.items():
            setattr(attempt, name, value)
    return bool(updated)


def finalize_pending(attempts):
    """
    Finalize every pending attempt among `attempts` that has an outcome,
    and flag scored ones whose prompt has since been flagged by moderation.

    One savepoint per attempt, so an attempt that can't be read is logged
    and the rest still finalize.
    """
    for attempt in with_status_data(attempts.filter(state=AttemptState.PENDING)):
        try:
            with transaction.atomic():
                finalize_attempt(attempt, attempt_status(attempt))
        except Exception:
            logger.exception('Hill attempt %s could not be finalized', attempt.id)
    # the battle doesn't wait for moderation, so a verdict can arrive after the score
    attempts.filter(
        state=AttemptState.SCORED,
        warrior__moderation_passed=False,
    ).update(state=AttemptState.FLAGGED)


def sweep_hill_attempts(now):
    """
    The scheduler's minute job: finalize what has finished, whether or not the hill is enabled.

    It reads open rounds and late attempts;
    the handover finalizes the round it closes.
    """
    finalize_pending(HillAttempt.objects.filter(
        Q(hill_round__closed_at=None) | Q(late=True),
    ))
