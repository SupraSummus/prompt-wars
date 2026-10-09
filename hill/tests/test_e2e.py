"""
An attack from submission to the crown, with the LLM and moderation mocked
and the battle played by the real goals.
"""
import pytest
from django.utils import timezone
from django_goals.busy_worker import worker
from django_goals.factories import GoalFactory
from django_goals.models import GoalState

from warriors.battles import LLM
from warriors.models import WarriorArena
from warriors.tests.factories import WarriorArenaFactory

from ..attack import submit_attack
from ..handover import hill_handover
from ..models import AttemptState, BossReason, Round
from ..rules import HILL_HANDOVER_GRACE, standings
from ..status import attempt_status, sweep_hill_attempts
from .fixtures import ATTACK, reload


@pytest.fixture
def ladder_boss(boss):
    """The boss also plays the ladder, in an arena of the hill's LLM."""
    return WarriorArenaFactory(warrior=boss, arena__llm=LLM.GOOGLE_GEMINI)


def send(request, hill_round, body=ATTACK):
    return submit_attack(
        request,
        round_number=hill_round.number,
        body=body,
        display_name='Riverstone',
    ).attempt


@pytest.mark.django_db
def test_an_attack_that_breaks_the_hill(moderation, gemini, hill_request, ladder_boss, open_round):
    gemini.return_value = (ATTACK, 'STOP', 'gemini-test')
    warrior_arenas = WarriorArena.objects.count()

    attempt = send(hill_request, open_round)
    worker(once=True)

    assert attempt_status(reload(attempt)) == AttemptState.SCORED
    sweep_hill_attempts(now=timezone.now())
    attempt.refresh_from_db()
    assert attempt.state == AttemptState.SCORED
    assert attempt.score > 0.55
    assert attempt.warrior.moderation_passed is True
    assert [row.attempt for row in standings(open_round)] == [attempt]

    hill_handover(now=open_round.ends_at + HILL_HANDOVER_GRACE)

    following = Round.objects.get(closed_at=None)
    assert (following.boss_attempt, following.boss_reason, following.boss_name) == (
        attempt, BossReason.BROKE, '',
    )
    # the crowning battle's replies and the names are moderated next, ahead of the ladder
    worker(once=True)
    attempt.refresh_from_db()
    assert attempt.output_moderation_passed is True
    following.refresh_from_db()
    assert following.boss_name == 'Riverstone'

    # the boss's ladder life never noticed
    ladder_boss.refresh_from_db()
    assert (ladder_boss.rating, ladder_boss.games_played) == (0.0, 0)
    assert WarriorArena.objects.count() == warrior_arenas


@pytest.mark.django_db
def test_an_attack_on_a_boss_whose_embedding_gave_up_still_scores_and_crowns(
    moderation, gemini, hill_request, boss, open_round,
):
    """The battle's embedding scores never finish, and the hill never needed them."""
    boss.voyage_3_embedding_goal = GoalFactory(handler='gave.up', state=GoalState.GIVEN_UP)
    boss.save(update_fields=['voyage_3_embedding_goal'])
    gemini.return_value = (ATTACK, 'STOP', 'gemini-test')

    attempt = send(hill_request, open_round)
    worker(once=True)

    loaded = reload(attempt)
    assert {game.processed_goal.state for game in loaded.battle.games_list} == {GoalState.NOT_GOING_TO_HAPPEN_SOON}
    assert attempt_status(loaded) == AttemptState.SCORED

    hill_handover(now=open_round.ends_at)
    assert Round.objects.get(closed_at=None).boss_attempt == attempt
