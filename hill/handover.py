"""
The daily handover: closing a round and deciding who holds the hill next.

Lock order is always the Hill row, then the open Round row:
here and in `hill_crown`.
An attack takes only the Round lock (`hill.attack.submit_attack`),
so it can never commit into a round the handover has closed.
"""
import dataclasses
import datetime
import logging

from django.db import transaction
from django.db.models import Q
from django_goals.models import schedule

from warriors.warriors import Warrior

from .models import (
    AttemptState, BossReason, CrownBlock, Hill, HillAttempt, Round,
)
from .rules import (
    HILL_HANDOVER_GRACE, HILL_HANDOVER_HOUR, HILL_MAX_REIGN_ROUNDS,
    HILL_MIN_ROUND, beats_boss, best_eligible,
)
from .status import finalize_pending
from .tasks import moderate_crowned_attempt


logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Successor:
    """Who holds the hill in the next round, how they got it, and the names it shows."""
    warrior: Warrior
    attempt: HillAttempt | None
    reason: str
    reign_round: int
    name: str = ''
    author: str = ''

    @classmethod
    def from_attempt(cls, attempt, reason):
        # unnamed until `moderate_crowned_attempt` passes the names typed for it
        return cls(warrior=attempt.warrior, attempt=attempt, reason=reason, reign_round=1)


def held(hill_round):
    """The round's boss, holding for one more round."""
    return Successor(
        warrior=hill_round.boss,
        attempt=hill_round.boss_attempt,
        reason=BossReason.HELD,
        reign_round=hill_round.reign_round + 1,
        name=hill_round.boss_name,
        author=hill_round.boss_author,
    )


def term_over(hill_round):
    """
    Whether the boss leaves at this handover even unbeaten:
    its term (`HILL_MAX_REIGN_ROUNDS`) ran out, or it was flagged (a takedown, say).
    """
    return (
        hill_round.reign_round >= HILL_MAX_REIGN_ROUNDS or
        not hill_round.boss_shown
    )


def decide_successor(hill, hill_round):
    """
    Who holds the hill after `hill_round`.

    The best eligible attempt of the boss's reign takes it if it beat the boss (`hill.rules.beats_boss`),
    or, once the term is over (`term_over`), although it lost its battle;
    otherwise the boss holds.
    Every candidate passed the no-return rule when it was sent.
    Why: "The crown rule" and "Rejected alternatives" in docs/king-of-the-hill.md.
    """
    reign = Round.objects.filter(
        hill=hill,
        boss_id=hill_round.boss_id,
        number__gt=hill_round.number - hill_round.reign_round,
        number__lte=hill_round.number,
    )
    best = best_eligible(HillAttempt.objects.filter(hill_round__in=reign))
    if best is None:
        return held(hill_round)
    if beats_boss(best):
        return Successor.from_attempt(best, BossReason.BROKE)
    if term_over(hill_round):
        return Successor.from_attempt(best, BossReason.INHERITED)
    return held(hill_round)


def round_end(starts_at):
    """
    When a round opened at `starts_at` ends: the first daily boundary (`HILL_HANDOVER_HOUR`)
    at least `HILL_MIN_ROUND` away, so no round is minutes long after a restart or a forced crown.
    """
    earliest = starts_at + HILL_MIN_ROUND
    boundary = earliest.astimezone(datetime.UTC).replace(hour=HILL_HANDOVER_HOUR, minute=0, second=0, microsecond=0)
    if boundary < earliest:
        boundary += datetime.timedelta(days=1)
    return boundary


def _open_round(hill, number, now, successor):
    return Round.objects.create(
        hill=hill,
        number=number,
        starts_at=now,
        ends_at=round_end(now),
        llm=hill.llm,
        boss=successor.warrior,
        boss_attempt=successor.attempt,
        boss_name=successor.name,
        boss_author=successor.author,
        boss_reason=successor.reason,
        reign_round=successor.reign_round,
    )


def close_round(hill, hill_round, now, forced=None):
    """
    Close `hill_round` and open the next one, under `forced` or the decided successor.

    The caller holds the Hill lock, then the Round lock.
    Pending attempts are finalized first, so one already scored counts and can be crowned;
    the ones still in battle become late: shown to their authors, never counted.
    A failing decision closes the round with the boss holding, logged,
    rather than leaving the hill stuck.
    """
    finalize_pending(hill_round.attempts.all())
    hill_round.attempts.filter(state=AttemptState.PENDING).update(late=True)
    successor = forced
    if successor is None:
        try:
            with transaction.atomic():
                successor = decide_successor(hill, hill_round)
        except Exception:
            logger.exception('Hill #%s: deciding the next boss failed; the boss holds', hill_round.number)
            successor = held(hill_round)

    hill_round.closed_at = now
    hill_round.save(update_fields=['closed_at'])

    next_round = _open_round(hill, hill_round.number + 1, now, successor)
    if (
        successor.reason in (BossReason.BROKE, BossReason.INHERITED) and
        successor.attempt.output_moderation_passed is None
    ):
        # the crowning battle goes public with the boss, so its replies and names need a verdict;
        # scheduled from the scheduler thread, so the deadline must be explicit
        schedule(moderate_crowned_attempt, args=[str(successor.attempt.id)], deadline=now)
    return next_round


def crown(hill, hill_round, successor, now):
    """
    Put `successor` on the hill at once: close the open round under it, or open the first round.

    The caller holds the Hill lock, then the open Round's, if there is one.
    """
    if hill_round is not None:
        return close_round(hill, hill_round, now, forced=successor)
    previous = hill.rounds.order_by('-number').first()
    number = previous.number + 1 if previous is not None else 1
    return _open_round(hill, number, now, successor)


def hill_handover(now):
    """
    The scheduler's minute job: close the open round once it has ended.

    Idempotent: a closed round has a successor whose `ends_at` is in the future.
    It waits up to `HILL_HANDOVER_GRACE` for attacks still in battle
    and for scored ones whose prompt has no moderation verdict yet,
    so a busy queue at the cutoff doesn't drop an attack that could take the hill.
    A disabled hill is left alone; re-enabled after its round ended, it hands over at once.
    """
    hill = Hill.current()
    if hill is None or not hill.enabled:
        return
    with transaction.atomic():
        hill = Hill.objects.select_for_update().get(id=hill.id)
        hill_round = Round.objects.select_for_update().filter(
            hill=hill,
            closed_at=None,
        ).first()
        if not hill.enabled or hill_round is None or now < hill_round.ends_at:
            return
        finalize_pending(hill_round.attempts.all())
        if now < hill_round.ends_at + HILL_HANDOVER_GRACE and hill_round.attempts.filter(
            Q(state=AttemptState.PENDING) |
            Q(state=AttemptState.SCORED, crown_block=CrownBlock.NONE, warrior__moderation_passed=None),
        ).exists():
            return
        close_round(hill, hill_round, now)
