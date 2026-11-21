import datetime

import pytest
from django.utils import timezone
from django_goals.models import Goal

from .. import handover
from ..handover import decide_successor, hill_handover, round_end
from ..models import AttemptState, BossReason, CrownBlock, Round
from ..rules import HILL_HANDOVER_GRACE, HILL_MAX_REIGN_ROUNDS, standings
from ..status import sweep_hill_attempts
from .factories import (
    HillAttemptFactory, RoundFactory, fought, resolve, scored,
)
from .fixtures import ATTACK


def at(text):
    return datetime.datetime.fromisoformat(text).replace(tzinfo=datetime.UTC)


@pytest.fixture
def reign(hill, boss):
    """A boss in the third and last round of its term: rounds 5 and 6 closed, 7 open."""
    now = timezone.now()
    rounds = [
        RoundFactory(hill=hill, boss=boss, number=number, reign_round=reign_round, closed_at=now)
        for number, reign_round in ((5, 1), (6, 2))
    ]
    rounds.append(RoundFactory(hill=hill, boss=boss, number=7, reign_round=3))
    return rounds


def successor(hill, hill_round):
    found = decide_successor(hill, hill_round)
    return found.reason, found.warrior, found.attempt, found.reign_round


@pytest.mark.django_db
@pytest.mark.parametrize('score, reason', [
    (0.4, BossReason.HELD),
    (0.54, BossReason.HELD),
    (0.55, BossReason.BROKE),
    (0.6, BossReason.BROKE),
])
def test_an_attacker_takes_the_hill_only_by_the_margin(hill, open_round, score, reason):
    attempt = scored(open_round, score)

    found = decide_successor(hill, open_round)

    assert found.reason == reason
    if reason == BossReason.BROKE:
        assert (found.warrior, found.attempt, found.reign_round) == (attempt.warrior, attempt, 1)


@pytest.mark.django_db
@pytest.mark.parametrize('kwargs', [
    {'crown_block': CrownBlock.TOO_LITTLE_SURVIVED},
    {'crown_block': CrownBlock.REPETITIVE_REPLY},
    {'late': True},
    {'warrior__moderation_passed': None},
    {'warrior__moderation_passed': False},
    {'state': AttemptState.FAILED},
], ids=['too little survived', 'repetitive', 'late', 'unmoderated', 'flagged', 'failed'])
def test_an_ineligible_winner_is_not_crowned(hill, open_round, kwargs):
    scored(open_round, 0.9, **kwargs)
    assert successor(hill, open_round)[0] == BossReason.HELD


@pytest.mark.django_db
def test_ties_go_to_more_survived_then_to_the_earliest(hill, open_round):
    now = timezone.now()
    scored(open_round, 0.6, survived_chars=100, created_at=now)
    later = scored(open_round, 0.6, survived_chars=200, created_at=now + datetime.timedelta(minutes=2))
    scored(open_round, 0.6, survived_chars=200, created_at=now + datetime.timedelta(minutes=3))
    assert successor(hill, open_round)[2] == later


@pytest.mark.django_db
def test_at_the_term_limit_the_best_of_the_reign_inherits(hill, reign):
    first_round, _, last_round = reign
    inheritor = scored(first_round, 0.3)
    scored(last_round, 0.2)
    assert successor(hill, last_round) == (BossReason.INHERITED, inheritor.warrior, inheritor, 1)


@pytest.mark.django_db
def test_an_attempt_from_before_the_reign_does_not_inherit(hill, reign):
    before = RoundFactory(hill=hill, number=4, closed_at=timezone.now())
    scored(before, 0.5)
    assert successor(hill, reign[-1]) == (BossReason.HELD, reign[-1].boss, None, 4)


@pytest.mark.django_db
@pytest.mark.parametrize('open_round, boss, reason', [
    ({'reign_round': HILL_MAX_REIGN_ROUNDS - 1}, {}, BossReason.HELD),
    ({'reign_round': HILL_MAX_REIGN_ROUNDS}, {}, BossReason.INHERITED),
    ({'reign_round': HILL_MAX_REIGN_ROUNDS + 1}, {}, BossReason.INHERITED),
    ({}, {'moderation_passed': False}, BossReason.INHERITED),
], indirect=['open_round', 'boss'], ids=['within its term', 'at its end', 'past it', 'boss taken down'])
def test_a_losing_attack_inherits_once_the_term_is_over(hill, open_round, reason):
    scored(open_round, 0.1)
    assert successor(hill, open_round)[0] == reason


@pytest.mark.parametrize('starts_at, ends_at', [
    ('2026-10-09T17:00', '2026-10-10T17:00'),
    # a forced crown just before the boundary runs to the next one but one
    ('2026-10-09T16:55', '2026-10-10T17:00'),
    ('2026-10-09T04:00', '2026-10-09T17:00'),
])
def test_a_round_ends_at_the_first_boundary_half_a_day_away(starts_at, ends_at):
    assert round_end(at(starts_at)) == at(ends_at)


def next_round(hill_round):
    return Round.objects.get(hill=hill_round.hill, number=hill_round.number + 1)


@pytest.fixture
def ended_round(open_round):
    """The open round, its end just reached."""
    open_round.ends_at = timezone.now() - datetime.timedelta(seconds=1)
    open_round.save(update_fields=['ends_at'])
    return open_round


@pytest.mark.django_db
def test_handover_waits_for_the_end(open_round):
    hill_handover(now=open_round.ends_at - datetime.timedelta(seconds=1))
    assert Round.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'enabled': False}], indirect=True)
def test_handover_leaves_a_disabled_hill_alone(hill, ended_round):
    hill_handover(now=timezone.now())
    assert Round.objects.count() == 1


@pytest.mark.django_db
def test_with_no_attackers_the_next_round_keeps_the_boss(ended_round):
    ended_round.boss_name = 'Founder'
    ended_round.save(update_fields=['boss_name'])
    now = timezone.now()

    hill_handover(now=now)

    ended_round.refresh_from_db()
    assert ended_round.closed_at == now
    following = next_round(ended_round)
    assert (following.boss, following.boss_attempt, following.boss_reason, following.reign_round) == (
        ended_round.boss, None, BossReason.HELD, 2,
    )
    assert following.boss_name == 'Founder'
    assert (following.starts_at, following.ends_at) == (now, round_end(now))
    assert following.closed_at is None


@pytest.mark.django_db
@pytest.mark.parametrize('attempt, after, waits', [
    ({}, datetime.timedelta(minutes=1), True),
    ({'state': AttemptState.SCORED, 'score': 0.3, 'warrior__moderation_passed': None}, datetime.timedelta(minutes=1), True),
    ({'state': AttemptState.SCORED, 'score': 0.9, 'warrior__moderation_passed': None}, HILL_HANDOVER_GRACE, False),
    ({'state': AttemptState.SCORED, 'score': 0.9, 'warrior__moderation_passed': None,
      'crown_block': CrownBlock.REPETITIVE_REPLY}, datetime.timedelta(minutes=1), False),
    ({'state': AttemptState.SCORED, 'score': 0.3}, datetime.timedelta(minutes=1), False),
], ids=['in battle', 'awaiting moderation', 'grace over', 'crown-blocked', 'settled'])
def test_the_handover_waits_within_the_grace_for_an_attack_still_unsettled(ended_round, attempt, after, waits):
    HillAttemptFactory(hill_round=ended_round, **attempt)
    hill_handover(now=ended_round.ends_at + after)
    ended_round.refresh_from_db()
    assert (ended_round.closed_at is None) is waits


@pytest.mark.django_db
def test_a_winner_scored_but_not_yet_finalized_is_crowned_without_waiting(ended_round):
    winner = fought(HillAttemptFactory(hill_round=ended_round, warrior__body=ATTACK), [ATTACK, ATTACK])
    now = ended_round.ends_at + datetime.timedelta(minutes=1)

    hill_handover(now=now)

    winner.refresh_from_db()
    assert winner.state == AttemptState.SCORED
    following = next_round(ended_round)
    assert (following.boss, following.boss_attempt, following.boss_reason) == (
        winner.warrior, winner, BossReason.BROKE,
    )
    # the crowning battle's replies and names are moderated before they go public, first in the queue
    (goal,) = Goal.objects.filter(handler='hill.tasks.moderate_crowned_attempt')
    assert goal.instructions == {'args': [str(winner.id)]}
    assert goal.deadline == now


@pytest.mark.django_db
def test_after_the_grace_an_attack_still_in_battle_is_late(ended_round):
    loser = scored(ended_round, 0.3)
    straggler = HillAttemptFactory(hill_round=ended_round, warrior__body=ATTACK)

    hill_handover(now=ended_round.ends_at + HILL_HANDOVER_GRACE)

    straggler.refresh_from_db()
    assert (straggler.state, straggler.late) == (AttemptState.PENDING, True)
    assert next_round(ended_round).boss_reason == BossReason.HELD

    # its result still arrives, for its author, but it never counts
    for game in straggler.battle.games_list:
        resolve(game, ATTACK)
    sweep_hill_attempts(now=timezone.now())
    straggler.refresh_from_db()
    assert (straggler.state, straggler.late) == (AttemptState.SCORED, True)
    assert straggler.score > 0.55
    assert [row.attempt for row in standings(ended_round)] == [loser]


@pytest.mark.django_db
def test_handover_runs_once(ended_round):
    now = timezone.now()
    hill_handover(now=now)
    hill_handover(now=now + datetime.timedelta(minutes=1))
    assert list(Round.objects.values_list('number', flat=True)) == [
        ended_round.number + 1, ended_round.number,
    ]


@pytest.mark.django_db
def test_a_failing_decision_closes_the_round_with_the_boss_holding(monkeypatch, ended_round):
    scored(ended_round, 0.9)
    monkeypatch.setattr(handover, 'decide_successor', lambda hill, hill_round: 1 / 0)

    hill_handover(now=timezone.now())

    ended_round.refresh_from_db()
    assert ended_round.closed_at is not None
    following = next_round(ended_round)
    assert (following.boss, following.boss_reason, following.reign_round) == (ended_round.boss, BossReason.HELD, 2)
