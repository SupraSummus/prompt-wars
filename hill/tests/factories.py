import datetime

import factory
from django.utils import timezone

from warriors.battles import LLM
from warriors.score import (
    ScoreAlgorithm, _ensure_score, get_or_create_game_score,
)
from warriors.tests.factories import BattleFactory, WarriorFactory
from warriors.text_unit import TextUnit

from ..models import AttemptState, BossReason, Hill, HillAttempt, Round


class HillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Hill

    enabled = True


def _the_hill():
    # one hill, as in production: `Hill.current()` reads the first
    return Hill.current() or HillFactory()


class RoundFactory(factory.django.DjangoModelFactory):
    """An open round of the hill that started an hour ago and runs for a day."""
    class Meta:
        model = Round

    hill = factory.LazyFunction(_the_hill)
    number = factory.Sequence(lambda n: n + 1)
    starts_at = factory.LazyFunction(lambda: timezone.now() - datetime.timedelta(hours=1))
    ends_at = factory.LazyAttribute(lambda o: o.starts_at + datetime.timedelta(days=1))
    llm = LLM.GOOGLE_GEMINI
    boss = factory.SubFactory(WarriorFactory)
    boss_reason = BossReason.OWNER


def _the_open_round():
    hill = _the_hill()
    return hill.rounds.filter(closed_at=None).first() or RoundFactory(hill=hill)


class HillAttemptFactory(factory.django.DjangoModelFactory):
    """A pending attempt, its battle unresolved, in the open round unless told otherwise; `scored` and `fought` give it more."""
    class Meta:
        model = HillAttempt

    hill_round = factory.LazyFunction(_the_open_round)
    warrior = factory.SubFactory(WarriorFactory)
    identity = factory.Sequence(lambda n: f'{n:032x}')
    battle = factory.SubFactory(
        BattleFactory,
        llm=factory.SelfAttribute('..hill_round.llm'),
        warrior_1=factory.SelfAttribute('..hill_round.boss'),
        warrior_2=factory.SelfAttribute('..warrior'),
        rated=False,
    )


def crown_attempt(hill, attempt, **kwargs):
    """Close `attempt`'s round and open the next one with it as the boss, as a handover would."""
    attempt.hill_round.closed_at = timezone.now()
    attempt.hill_round.save(update_fields=['closed_at'])
    return RoundFactory(**{
        'hill': hill,
        'number': attempt.hill_round.number + 1,
        'boss': attempt.warrior,
        'boss_attempt': attempt,
        'boss_reason': BossReason.BROKE,
        **kwargs,
    })


def scored(hill_round, score, survived_chars=100, **kwargs):
    """A scored attempt with the numbers finalize would have written, its battle left unresolved."""
    return HillAttemptFactory(**{
        'hill_round': hill_round,
        'state': AttemptState.SCORED,
        'score': score,
        'survived_chars': survived_chars,
        **kwargs,
    })


def resolve(game, result, finish_reason='STOP', attempts=0, score=True):
    """Resolve `game` to `result`, as its resolve goal would, and score it by LCS unless told not to."""
    game.text_unit = TextUnit.get_or_create_by_content(result)
    game.finish_reason = finish_reason
    game.attempts = attempts
    game.resolved_at = timezone.now()
    game.save()
    if score:
        _ensure_score(get_or_create_game_score(game, ScoreAlgorithm.LCS))
    return game


def fought(attempt, results, **kwargs):
    """`attempt` with its battle resolved to `results`, one per game, and scored."""
    for game, result in zip(attempt.battle.games_list, results):
        resolve(game, result, **kwargs)
    return attempt
