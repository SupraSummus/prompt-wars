"""
The hill's moderation goals.

The hill moderates on its own client rather than through `do_moderation`:
a timeout and no SDK retries, so a hung call can't hold a worker thread for long,
transient errors retried instead of given up,
and no naming or embedding scheduled after it —
hill spells keep blank names and never need an embedding.
"""
import datetime
import functools

import openai
from django.utils import timezone
from django_goals.models import AllDone, RetryMeLater

from warriors.llms.openai import openai_client
from warriors.warriors import Warrior

from .models import HillAttempt, Round


MODERATION_MODEL = 'omni-moderation-latest'
# Seconds before a moderation call is abandoned; a retry costs less than a pinned thread.
HILL_MODERATION_TIMEOUT = 20
# Wait before retrying a transient error: short enough that a blip barely delays the verdict,
# long enough not to hammer a rate-limited endpoint.
HILL_MODERATION_RETRY = datetime.timedelta(seconds=30)

moderation_client = openai_client.with_options(
    timeout=HILL_MODERATION_TIMEOUT,
    max_retries=0,
)

# rate limits, timeouts and connection errors, and 5xx
TRANSIENT_MODERATION_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def moderate(texts):
    """Moderate `texts` in one call; one result per text, in order."""
    return moderation_client.moderations.create(
        model=MODERATION_MODEL,
        input=list(texts),
    )


def record_spell_moderation(warrior, response, flagged, now):
    """Store a spell's verdict, unless another moderation stored one first."""
    Warrior.objects.filter(
        id=warrior.id,
        moderation_passed=None,
    ).update(
        moderation_passed=not flagged,
        moderation_model=response.model,
        moderation_date=now,
    )


def retry_when_unavailable(handler):
    """Have a moderation goal answer a transient error with a retry in `HILL_MODERATION_RETRY`."""
    @functools.wraps(handler)
    def wrapper(goal, *args):
        try:
            return handler(goal, *args)
        except TRANSIENT_MODERATION_ERRORS:
            return RetryMeLater(
                precondition_date=timezone.now() + HILL_MODERATION_RETRY,
                message='Moderation unavailable',
            )
    return wrapper


@retry_when_unavailable
def moderate_attempt(goal, attempt_id):
    """
    Moderate an attack's spell, which gates its crown.

    A flagged spell turns its attempt flagged (`hill.status.attempt_status`).
    """
    warrior = HillAttempt.objects.select_related('warrior').get(id=attempt_id).warrior
    response = moderate([warrior.body])
    (result,) = response.results
    record_spell_moderation(warrior, response, result.flagged, timezone.now())
    return AllDone()


@retry_when_unavailable
def moderate_crowned_attempt(goal, attempt_id):
    """
    Moderate what an attack that took the hill publishes besides its spell, in one call:
    both replies of its battle, and the names typed for it.

    Passed replies may be shown to anyone (`hill.rules.replies_public`).
    Passed names go onto every round its spell holds;
    flagged ones never do, and the boss reigns unnamed.
    """
    attempt = HillAttempt.objects.select_related('battle').get(id=attempt_id)
    replies = [game.result for game in attempt.battle.games_list]
    names = '\n'.join(filter(None, [attempt.display_name, attempt.display_author]))
    results = list(moderate(replies + ([names] if names else [])).results)
    HillAttempt.objects.filter(id=attempt.id).update(
        output_moderation_passed=not any(result.flagged for result in results[:len(replies)]),
    )
    if names and not results[-1].flagged:
        Round.objects.filter(boss_attempt=attempt).update(
            boss_name=attempt.display_name,
            boss_author=attempt.display_author,
        )
    return AllDone()
