import httpx
import openai
import pytest
from django.utils import timezone
from django_goals.models import Goal, RetryMeLater

from ..models import AttemptState, BossReason, Round
from ..status import attempt_status
from ..tasks import (
    HILL_MODERATION_RETRY, moderate_attempt, moderate_crowned_attempt,
)
from .factories import HillAttemptFactory, RoundFactory, crown_attempt, fought
from .fixtures import ATTACK, reload


# one of the errors the hill's moderation retries (`hill.tasks.TRANSIENT_MODERATION_ERRORS`)
TRANSIENT_ERROR = openai.APIConnectionError(request=httpx.Request('POST', 'https://api.openai.com/v1/moderations'))


def unmoderated_attempt(open_round):
    return HillAttemptFactory(hill_round=open_round, warrior__body=ATTACK, warrior__moderation_passed=None)


@pytest.mark.django_db
def test_an_attacks_prompt_is_moderated(moderation, open_round):
    attempt = unmoderated_attempt(open_round)

    moderate_attempt(None, str(attempt.id))

    assert moderation.calls == [[ATTACK]]
    attempt.warrior.refresh_from_db()
    assert (attempt.warrior.moderation_passed, attempt.warrior.moderation_model) == (True, 'omni-moderation-latest')
    assert attempt.warrior.moderation_date is not None
    # hill warriors get no generated name and no embedding
    assert not Goal.objects.exists()


@pytest.mark.django_db
def test_a_flagged_prompt_flags_its_attempt(moderation, open_round):
    attempt = fought(unmoderated_attempt(open_round), [ATTACK, ATTACK])
    moderation.flagged.add(ATTACK)

    moderate_attempt(None, str(attempt.id))

    loaded = reload(attempt)
    assert loaded.warrior.moderation_passed is False
    assert attempt_status(loaded) == AttemptState.FLAGGED


@pytest.mark.django_db
@pytest.mark.parametrize('flagged, passed', [(set(), True), ({'a reply with a slur'}, False)])
def test_both_replies_of_a_crowned_attack_are_moderated_together(moderation, open_round, flagged, passed):
    attempt = fought(HillAttemptFactory(hill_round=open_round), ['a reply with a slur', 'a clean reply'])
    moderation.flagged.update(flagged)

    moderate_crowned_attempt(None, str(attempt.id))

    assert moderation.calls == [['a reply with a slur', 'a clean reply']]
    attempt.refresh_from_db()
    assert attempt.output_moderation_passed is passed


@pytest.mark.django_db
@pytest.mark.parametrize('flagged, names', [(False, ('Riverstone', 'Ana')), (True, ('', ''))])
def test_names_go_on_every_round_of_their_boss_once_they_pass(moderation, hill, open_round, flagged, names):
    attempt = fought(
        HillAttemptFactory(hill_round=open_round, display_name='Riverstone', display_author='Ana'),
        ['one', 'two'],
    )
    first = crown_attempt(hill, attempt)
    first.closed_at = timezone.now()
    first.save(update_fields=['closed_at'])
    RoundFactory(
        hill=hill, number=first.number + 1, boss=attempt.warrior, boss_attempt=attempt,
        boss_reason=BossReason.HELD, reign_round=2,
    )
    if flagged:
        moderation.flagged.add('Riverstone\nAna')

    moderate_crowned_attempt(None, str(attempt.id))

    assert moderation.calls == [['one', 'two', 'Riverstone\nAna']]
    assert list(Round.objects.filter(boss_attempt=attempt).values_list('boss_name', 'boss_author')) == [names] * 2


@pytest.mark.django_db
@pytest.mark.parametrize('task', [moderate_attempt, moderate_crowned_attempt], ids=lambda task: task.__name__)
def test_moderation_retries_when_unavailable(moderation, open_round, task):
    attempt = fought(unmoderated_attempt(open_round), ['one', 'two'])
    moderation.error = TRANSIENT_ERROR
    before = timezone.now()

    result = task(None, str(attempt.id))

    assert isinstance(result, RetryMeLater)
    assert before + HILL_MODERATION_RETRY <= result.precondition_date <= timezone.now() + HILL_MODERATION_RETRY
    attempt.refresh_from_db()
    attempt.warrior.refresh_from_db()
    assert (attempt.warrior.moderation_passed, attempt.output_moderation_passed) == (None, None)
