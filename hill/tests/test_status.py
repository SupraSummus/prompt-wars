import datetime

import pytest
from django.utils import timezone
from django_goals.factories import GoalFactory
from django_goals.models import GoalState

from warriors.score import ScoreAlgorithm, get_or_create_game_score
from warriors.tasks import MAX_TRANSIENT_RETRIES

from .. import status
from ..models import AttemptState, CrownBlock, HillAttempt
from ..status import (
    attempt_status, finalize_attempt, stage_key, sweep_hill_attempts,
)
from .factories import HillAttemptFactory, fought, resolve
from .fixtures import ATTACK, reload


def status_of(attempt):
    return attempt_status(reload(attempt))


def gave_up():
    return GoalFactory(handler='gave.up', state=GoalState.GIVEN_UP)


@pytest.fixture
def attempt(open_round):
    return HillAttemptFactory(hill_round=open_round, warrior__body=ATTACK)


@pytest.mark.django_db
@pytest.mark.parametrize('scored_rows', [False, True], ids=['one game resolved', 'scores without similarities'])
def test_an_attack_waiting_for_its_scores_is_pending(attempt, scored_rows):
    games = attempt.battle.games_list
    if scored_rows:
        for game in games:
            resolve(game, ATTACK, score=False)
            get_or_create_game_score(game, ScoreAlgorithm.LCS)
    else:
        resolve(games[0], ATTACK)
    assert status_of(attempt) == AttemptState.PENDING


@pytest.mark.django_db
@pytest.mark.parametrize('results, finish_reason, attempts, expected', [
    (['', ''], 'error', MAX_TRANSIENT_RETRIES + 1, AttemptState.VOID),
    (['', ''], 'error', 0, AttemptState.FAILED),
    (['', ''], 'error', MAX_TRANSIENT_RETRIES, AttemptState.FAILED),
    (['', ''], 'STOP', 0, AttemptState.FAILED),
    (['', ATTACK], 'STOP', 0, AttemptState.FAILED),
    ([ATTACK, ATTACK], 'STOP', 0, AttemptState.SCORED),
], ids=['retries ran out', 'no candidate', 'content error after retries', 'empty stop', 'one empty', 'echo'])
def test_how_a_resolved_battle_ends(attempt, results, finish_reason, attempts, expected):
    fought(attempt, results, finish_reason=finish_reason, attempts=attempts)
    assert status_of(attempt) == expected


@pytest.mark.django_db
@pytest.mark.parametrize('gave_up_on', ['resolving', 'scoring a resolved game', 'the score'])
def test_a_goal_that_gave_up_before_the_score_voids_the_attack(attempt, gave_up_on):
    first, second = attempt.battle.games_list
    resolve(first, ATTACK)
    if gave_up_on == 'resolving':
        second.processed_goal = gave_up()
        second.save(update_fields=['processed_goal'])
    elif gave_up_on == 'scoring a resolved game':
        resolve(second, ATTACK, score=False)
        second.processed_goal = gave_up()
        second.save(update_fields=['processed_goal'])
    else:
        resolve(second, ATTACK, score=False)
        score = get_or_create_game_score(second, ScoreAlgorithm.LCS)
        score.processed_goal = gave_up()
        score.save(update_fields=['processed_goal'])
    assert status_of(attempt) == AttemptState.VOID


@pytest.mark.django_db
def test_a_flagged_prompt_is_flagged_even_once_scored(attempt):
    fought(attempt, [ATTACK, ATTACK])
    attempt.warrior.moderation_passed = False
    attempt.warrior.save(update_fields=['moderation_passed'])
    assert status_of(attempt) == AttemptState.FLAGGED


@pytest.mark.django_db
def test_a_stored_outcome_stands(attempt):
    attempt.state = AttemptState.FAILED
    attempt.save(update_fields=['state'])
    fought(attempt, [ATTACK, ATTACK])
    assert status_of(attempt) == AttemptState.FAILED


@pytest.mark.django_db
def test_stage_key(attempt):
    now = timezone.now()
    assert stage_key(reload(attempt), AttemptState.PENDING, now) == 'pending'
    assert stage_key(reload(attempt), AttemptState.PENDING, now + datetime.timedelta(minutes=6)) == 'pending+slow'
    assert stage_key(reload(attempt), AttemptState.SCORED, now) == 'scored'


@pytest.mark.django_db
def test_finalize_stores_the_score_once(attempt):
    attempt.late = True
    attempt.save(update_fields=['late'])
    fought(attempt, [ATTACK, ATTACK])
    loaded = reload(attempt)

    assert finalize_attempt(loaded, attempt_status(loaded))
    assert not finalize_attempt(reload(attempt), AttemptState.VOID)

    attempt.refresh_from_db()
    assert attempt.state == AttemptState.SCORED
    assert attempt.score == attempt.battle.warrior_score(attempt.warrior_id, ScoreAlgorithm.LCS) > 0.5
    # the whole prompt survived, in both games
    assert attempt.survived_chars == 2 * len(ATTACK)
    assert attempt.crown_block == CrownBlock.NONE
    assert attempt.late


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'enabled': False}], indirect=True)
def test_sweep_finalizes_what_has_finished(monkeypatch, open_round, earlier_round):
    """Even with the hill disabled, and even when one attempt can't be read."""
    now = timezone.now()
    finished = fought(HillAttemptFactory(hill_round=open_round, warrior__body=ATTACK), [ATTACK, ATTACK])
    unreadable = fought(HillAttemptFactory(hill_round=open_round), [ATTACK, ATTACK])
    # an attack with a battle is never voided by time: it waits as long as its battle does
    waiting = HillAttemptFactory(hill_round=open_round, created_at=now - datetime.timedelta(hours=6))
    late = fought(HillAttemptFactory(hill_round=earlier_round, late=True), [ATTACK, ATTACK])
    flagged_since = fought(HillAttemptFactory(hill_round=open_round), [ATTACK, ATTACK])
    finalize_attempt(reload(flagged_since), AttemptState.SCORED)
    flagged_since.warrior.moderation_passed = False
    flagged_since.warrior.save(update_fields=['moderation_passed'])

    real_status = status.attempt_status

    def attempt_status_failing_once(attempt):
        if attempt.id == unreadable.id:
            raise ValueError('unexpected rows')
        return real_status(attempt)

    monkeypatch.setattr(status, 'attempt_status', attempt_status_failing_once)

    sweep_hill_attempts(now=now)

    states = {
        attempt: HillAttempt.objects.get(id=attempt.id).state
        for attempt in (finished, unreadable, waiting, late, flagged_since)
    }
    assert states == {
        finished: AttemptState.SCORED,
        unreadable: AttemptState.PENDING,
        waiting: AttemptState.PENDING,
        late: AttemptState.SCORED,
        flagged_since: AttemptState.FLAGGED,
    }
