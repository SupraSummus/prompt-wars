import pytest
from django.utils import timezone
from django_goals.models import Goal

from warriors.models import WarriorArena, WarriorUserPermission
from warriors.tests.factories import WarriorFactory

from ..attack import Refused, captcha_needed, submit_attack
from ..handover import close_round, hill_handover
from ..identity import SESSION_KEY, get_identity, peek_identity
from ..models import AttemptState, HillAttempt, Round
from ..rules import HILL_ATTEMPTS_PER_PLAYER, HILL_NO_RETURN_ROUNDS
from .factories import HillAttemptFactory, RoundFactory
from .fixtures import ATTACK, new_request


def attack(request, hill_round, body=ATTACK, **kwargs):
    kwargs.setdefault('round_number', hill_round.number)
    return submit_attack(request, body=body, **kwargs)


def refusal(request, hill_round, body=ATTACK, **kwargs):
    with pytest.raises(Refused) as caught:
        attack(request, hill_round, body, **kwargs)
    return caught.value.code


def goals(handler):
    return list(Goal.objects.filter(handler=handler))


@pytest.mark.django_db
def test_an_attack_starts_its_battle_at_once(hill_request, open_round):
    accepted = attack(hill_request, open_round, display_name='Riverstone', display_author='Ana')

    attempt = accepted.attempt
    assert not accepted.repeated
    assert attempt.hill_round == open_round
    assert (attempt.state, attempt.identity) == (AttemptState.PENDING, peek_identity(hill_request))
    assert (attempt.display_name, attempt.display_author) == ('Riverstone', 'Ana')

    warrior = attempt.warrior
    assert (warrior.body, warrior.name, warrior.author_name, warrior.created_by) == (ATTACK, '', '', None)
    assert warrior.moderation_passed is None
    # nothing enrolls the warrior on the ladder or grants it to anyone
    assert not WarriorArena.objects.filter(warrior=warrior).exists()
    assert not WarriorUserPermission.objects.filter(warrior=warrior).exists()
    assert 'authorized_warriors' not in hill_request.session

    battle = attempt.battle
    assert (battle.rated, battle.arena, battle.llm) == (False, None, open_round.llm)
    assert {battle.warrior_1, battle.warrior_2} == {open_round.boss, warrior}
    assert [game.processed_goal.deadline for game in battle.games_list] == [attempt.created_at] * 2
    assert not goals('warriors.tasks.transfer_rating')

    (moderation,) = goals('hill.tasks.moderate_attempt')
    assert moderation.instructions == {'args': [str(attempt.id)]}
    assert moderation.deadline == attempt.created_at

    assert hill_request.session.modified


@pytest.mark.django_db
def test_the_captcha_is_asked_once_per_round(hill, hill_request, open_round):
    assert captcha_needed(hill_request, open_round, peek_identity(hill_request))
    attack(hill_request, open_round)
    # whatever became of the attack
    HillAttempt.objects.update(state=AttemptState.FAILED)
    assert not captcha_needed(hill_request, open_round, peek_identity(hill_request))

    open_round.ends_at = timezone.now()
    open_round.save(update_fields=['ends_at'])
    following = close_round(hill, open_round, timezone.now())
    assert captcha_needed(hill_request, following, peek_identity(hill_request))


@pytest.mark.django_db
def test_the_form_of_a_previous_round_is_refused(hill_request, open_round):
    assert refusal(hill_request, open_round, round_number=open_round.number - 1) == 'round_changed'


@pytest.mark.django_db
@pytest.mark.parametrize('open_round', [{'number': 20}], indirect=True)
@pytest.mark.parametrize('rounds_ago, refused', [
    (3, True),
    (HILL_NO_RETURN_ROUNDS, True),
    (HILL_NO_RETURN_ROUNDS + 1, False),
])
def test_a_recent_boss_cannot_return(hill, hill_request, open_round, rounds_ago, refused):
    """Its own author tries it, so only the no-return rule stands in the way."""
    crowned_in = RoundFactory(hill=hill, number=open_round.number - rounds_ago - 1, closed_at=timezone.now())
    old_boss = HillAttemptFactory(
        hill_round=crowned_in, identity=get_identity(hill_request),
        warrior__body=ATTACK, state=AttemptState.SCORED,
    ).warrior
    RoundFactory(hill=hill, number=open_round.number - rounds_ago, boss=old_boss, closed_at=timezone.now())

    if refused:
        assert refusal(hill_request, open_round) == 'copies_boss'
        assert refusal(hill_request, open_round, ATTACK + ' Plus a new ending.') == 'copies_boss'
    else:
        assert attack(hill_request, open_round).attempt.warrior == old_boss


@pytest.mark.django_db
def test_someone_elses_text_is_refused(rf, user, hill_request, open_round):
    # a ladder prompt, even its author's own
    ladder = WarriorFactory(body=ATTACK, created_by=user)
    assert refusal(hill_request, open_round) == 'exists'
    assert refusal(new_request(rf, user=user), open_round) == 'exists'
    # another player's hill prompt
    others = HillAttemptFactory(hill_round=open_round, warrior__body='My hill spell, sealed.')
    assert refusal(hill_request, open_round, others.warrior.body) == 'exists'
    assert list(HillAttempt.objects.all()) == [others]
    assert not ladder.hill_attempts.exists()


@pytest.mark.django_db
def test_a_player_may_bring_back_their_own_hill_prompt(hill_request, earlier_round, open_round):
    earlier = HillAttemptFactory(
        hill_round=earlier_round, identity=get_identity(hill_request),
        warrior__body=ATTACK, state=AttemptState.SCORED,
    )

    attempt = attack(hill_request, open_round).attempt

    assert attempt.warrior == earlier.warrior
    # moderated already
    assert not goals('hill.tasks.moderate_attempt')


@pytest.mark.django_db
@pytest.mark.parametrize('resent', [ATTACK, ATTACK.upper(), ATTACK.replace(' ', '   ').replace(',', '')])
def test_resending_a_prompt_in_a_round_leads_back_to_it_for_free(rf, hill_request, open_round, resent):
    """Even while it is in battle, and with the player at the cap."""
    first = attack(hill_request, open_round).attempt
    HillAttemptFactory.create_batch(
        HILL_ATTEMPTS_PER_PLAYER - 1, hill_round=open_round, identity=first.identity, state=AttemptState.FAILED,
    )

    again = attack(new_request(rf, session=hill_request.session), open_round, resent)

    assert (again.attempt, again.repeated) == (first, True)
    assert HillAttempt.objects.count() == HILL_ATTEMPTS_PER_PLAYER


@pytest.mark.django_db
def test_a_flagged_text_is_refused_even_to_its_author(hill_request, earlier_round, open_round):
    HillAttemptFactory(
        hill_round=earlier_round, identity=get_identity(hill_request),
        warrior__body=ATTACK, warrior__moderation_passed=False, state=AttemptState.SCORED,
    )
    assert refusal(hill_request, open_round) == 'flagged'


@pytest.mark.django_db
@pytest.mark.parametrize('states, allowed', [
    ([AttemptState.SCORED] * 4, True),
    ([AttemptState.SCORED, AttemptState.FAILED, AttemptState.FLAGGED, AttemptState.SCORED, AttemptState.FAILED], False),
    ([AttemptState.SCORED] * 4 + [AttemptState.VOID], True),
], ids=['under the cap of 5', 'every outcome counts', 'void is refunded'])
def test_the_per_player_cap(hill_request, open_round, states, allowed):
    identity = get_identity(hill_request)
    for state in states:
        HillAttemptFactory(hill_round=open_round, identity=identity, state=state)
    if allowed:
        attack(hill_request, open_round)
    else:
        assert refusal(hill_request, open_round) == 'player_cap'


@pytest.mark.django_db
def test_one_attack_at_a_time(hill_request, earlier_round, open_round):
    # even one left in battle in the previous round
    HillAttemptFactory(hill_round=earlier_round, identity=get_identity(hill_request), late=True)
    assert refusal(hill_request, open_round) == 'in_flight'


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'max_pending': 2}], indirect=True)
def test_a_full_queue_refuses(hill_request, open_round):
    HillAttemptFactory.create_batch(2, hill_round=open_round)
    assert refusal(hill_request, open_round) == 'busy'


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'daily_attempt_limit': 2}], indirect=True)
# a void attempt is refunded to its player, but its battle may have cost money
@pytest.mark.parametrize('state', [AttemptState.SCORED, AttemptState.VOID])
def test_a_spent_budget_refuses(hill_request, open_round, state):
    HillAttemptFactory.create_batch(2, hill_round=open_round, state=state)
    assert refusal(hill_request, open_round) == 'used_up'


@pytest.mark.django_db
def test_an_ended_round_waiting_for_its_handover_takes_no_attacks(hill_request, open_round):
    open_round.ends_at = timezone.now()
    open_round.save(update_fields=['ends_at'])
    assert refusal(hill_request, open_round) == 'crowning'


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'enabled': False}], indirect=True)
def test_a_disabled_hill_is_closed(hill_request, open_round):
    assert refusal(hill_request, open_round) == 'closed'
    # and the visitor gets no identity from trying
    assert SESSION_KEY not in hill_request.session


@pytest.mark.django_db
def test_an_attack_racing_the_handover_is_refused(monkeypatch, hill_request, open_round):
    """The handover closes the round after the attack read it and before the attack takes its lock."""
    read_before = Round.objects.open_in(open_round.hill)
    open_round.ends_at = timezone.now()
    open_round.save(update_fields=['ends_at'])
    hill_handover(now=timezone.now())
    monkeypatch.setattr(type(Round.objects), 'open_in', lambda self, hill: read_before)

    assert refusal(hill_request, open_round) == 'round_changed'
    assert not HillAttempt.objects.exists()
