"""
Accepting an attack on the hill: the entry checks, then the battle.

The attack form parses the input (`hill.forms.HillAttackForm`);
`submit_attack` applies the game's rules to it and starts the battle.
"""
import dataclasses

from django.db import transaction
from django.utils import timezone
from django_goals.models import schedule

from warriors.battles import Battle
from warriors.warriors import (
    Warrior, get_or_insert_warrior, normalize_spell_body,
)

from .identity import get_identity
from .models import AttemptState, Hill, HillAttempt, Round
from .rules import HILL_ATTEMPTS_PER_PLAYER, budget_used, recent_bosses
from .similarity import HILL_BOSS_COPY_THRESHOLD, copied_share, skeleton
from .tasks import moderate_attempt


# The round an identity last passed the captcha in.
VERIFIED_ROUND_SESSION_KEY = 'hill_verified_round'


class Refused(Exception):
    """An attack the hill turns down; `code` names the check, for the page to pick its state by."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclasses.dataclass(frozen=True)
class Accepted:
    attempt: HillAttempt
    # The player sent a spell they already sent this round,
    # and `attempt` is that earlier attack: nothing new was charged or fought.
    repeated: bool = False

    REPEAT_NOTICE = (
        "You already sent this spell this round "
        "(spacing, case and punctuation don't count as changes)."
    )


def round_refusal(hill, hill_round, now):
    """Refuse unless the hill is on and its round takes attacks at `now`."""
    if hill is None or not hill.enabled:
        return Refused('closed', 'King of the Hill is closed.')
    if hill_round is None:
        return Refused('opens_soon', 'The hill opens soon.')
    if hill_round.closed_at is not None:
        return Refused(
            'round_changed',
            'The hill changed hands while you were writing; here is the new boss.',
        )
    if now >= hill_round.ends_at:
        return Refused(
            'crowning',
            f'Hill #{hill_round.number} has closed and its next boss is being crowned. '
            'Try again in a few minutes.',
        )
    return None


def admission_refusal(hill, hill_round, identity):
    """
    Refuse an attack the hill has no room for.

    The player's cap and the player's previous attack still in battle,
    then the round's budget and the global queue (`Hill.max_pending`).
    The player's own limits come first: they hold whatever the budget and the queue do,
    and "send it again in a minute" would bring a capped player back only to be refused again.
    With no identity, the player's limits are skipped.
    """
    if identity is not None:
        attempts = HillAttempt.objects.filter(identity=identity)
        if attempts.filter(hill_round=hill_round).live().count() >= HILL_ATTEMPTS_PER_PLAYER:
            return Refused(
                'player_cap',
                f"You've used your {HILL_ATTEMPTS_PER_PLAYER} attacks on Hill #{hill_round.number}.",
            )
        if attempts.filter(state=AttemptState.PENDING).exists():
            return Refused('in_flight', "Your last attack's battle isn't over yet.")
    if budget_used(hill_round) >= hill.daily_attempt_limit:
        return Refused(
            'used_up',
            f"This round's attacks are used up. Hill #{hill_round.number + 1} "
            f'opens at {hill_round.ends_at:%H:%M} UTC.',
        )
    pending = HillAttempt.objects.filter(state=AttemptState.PENDING).count()
    if pending >= hill.max_pending:
        return Refused(
            'busy',
            f'Busy right now: {pending} attacks are in battle. '
            'Your text is kept; send it again in a minute.',
        )
    return None


def entry_refusal(hill, hill_round, identity, now):
    """What keeps the visitor from attacking right now, before they write anything; None if nothing."""
    return round_refusal(hill, hill_round, now) or admission_refusal(hill, hill_round, identity)


def captcha_needed(request, hill_round, identity):
    """
    Whether this attack needs a captcha: only an identity's first in a round.

    Iterating is the core loop, and a checkbox captcha escalates on repeated solves;
    the round budget, not the captcha, is what bounds cost.
    A solved captcha counts for the round even if the attack it came with was refused.
    """
    if identity is not None and hill_round.attempts.filter(identity=identity).exists():
        return False
    return request.session.get(VERIFIED_ROUND_SESSION_KEY) != str(hill_round.id)


def _repeated_attempt(hill_round, identity, body, body_sha_256):
    """
    The identity's live attempt this round with the same spell, by hash or by skeleton.

    At temperature 0 the same spell mostly replays the same battle,
    and a variant in spacing, case or punctuation is not a new idea,
    so neither earns another roll.
    Compared in Python: an identity has at most `HILL_ATTEMPTS_PER_PLAYER` live attempts.
    """
    body_skeleton = skeleton(body)
    for attempt in hill_round.attempts.live().filter(identity=identity).select_related('warrior'):
        if (
            bytes(attempt.warrior.body_sha_256) == body_sha_256 or
            skeleton(attempt.warrior.body) == body_skeleton
        ):
            return attempt
    return None


def _copy_refusal(hill_round, body):
    """
    Refuse a copy of the boss, or of a boss of the last `HILL_NO_RETURN_ROUNDS` rounds.

    A spell can't fight itself, and a dethroned boss's family can't alternate with its conqueror.
    """
    for boss in recent_bosses(hill_round):
        share = copied_share(boss.body, body)
        if share >= HILL_BOSS_COPY_THRESHOLD:
            whose = "the boss's" if boss.id == hill_round.boss_id else "a recent boss's"
            return Refused(
                'copies_boss',
                f'Your spell copies {whose} text ({share:.0%} match). The hill needs your own words.',
            )
    return None


def _warrior_refusal(warrior, identity):
    """
    Refuse a spell whose text already exists (`warrior`, None if it doesn't),
    unless it is this player's own hill text.

    A ladder text, or another player's, would otherwise be published on the hill
    by someone who is not its author,
    and pasting someone's text would let a sniper fight with it.
    """
    if warrior is None:
        return None
    if warrior.moderation_passed is False:
        return Refused('flagged', 'This text was flagged by moderation.')
    if not HillAttempt.objects.filter(warrior=warrior, identity=identity).exists():
        return Refused(
            'exists',
            'This exact text already exists. Change something to make it yours.',
        )
    return None


def submit_attack(request, *, round_number, body, display_name='', display_author=''):
    """
    Attack the hill's boss with `body`; `Accepted`, or raises `Refused`.

    The checks run under the open Round's row lock, which the handover also takes,
    so an attack never lands in a round the handover has closed,
    and two attacks with one new text serialize: the second finds the first's Warrior.
    The battle starts at once, ahead of the spell's moderation:
    the first result is what the hill is for, and a spell flagged meanwhile is never shown or crowned.
    """
    hill = Hill.current()
    hill_round = Round.objects.open_in(hill)
    refusal = round_refusal(hill, hill_round, timezone.now())
    if refusal is not None:
        raise refusal
    if round_number != hill_round.number:
        raise Refused('round_changed', 'The hill changed hands while you were writing; here is the new boss.')
    body, body_sha_256 = normalize_spell_body(body)
    identity = get_identity(request)

    with transaction.atomic():
        hill_round = Round.objects.select_for_update(of=('self',)).select_related(
            'hill', 'boss',
        ).get(id=hill_round.id)
        now = timezone.now()
        refusal = round_refusal(hill_round.hill, hill_round, now)
        if refusal is not None:
            raise refusal
        # a repeat is charged nothing, so it is answered before any limit
        earlier = _repeated_attempt(hill_round, identity, body, body_sha_256)
        if earlier is not None:
            return Accepted(earlier, repeated=True)
        warrior = Warrior.objects.filter(body_sha_256=body_sha_256).first()
        refusal = (
            _copy_refusal(hill_round, body) or
            _warrior_refusal(warrior, identity) or
            admission_refusal(hill_round.hill, hill_round, identity)
        )
        if refusal is None and warrior is None:
            warrior, created = get_or_insert_warrior(body, body_sha_256)
            # the ladder, which doesn't take this lock, may have inserted the text meanwhile
            refusal = None if created else _warrior_refusal(warrior, identity)
        if refusal is not None:
            raise refusal

        attempt = HillAttempt.objects.create(
            hill_round=hill_round,
            warrior=warrior,
            identity=identity,
            display_name=display_name,
            display_author=display_author,
            created_at=now,
            battle=Battle.create(
                llm=hill_round.llm,
                warrior_a=hill_round.boss,
                warrior_b=warrior,
                rated=False,
                deadline=now,
            ),
        )
        if warrior.moderation_passed is None:
            schedule(moderate_attempt, args=[str(attempt.id)], deadline=now)

    # keeps an active player's session cookie from expiring
    request.session.modified = True
    return Accepted(attempt)
