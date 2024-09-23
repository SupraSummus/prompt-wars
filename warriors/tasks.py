import datetime
import logging
import random

from django.db import transaction
from django.db.models.functions import Abs
from django.utils import timezone
from django_goals.models import AllDone, RetryMeLater

from . import anthropic
from .exceptions import RateLimitError
from .lcs import lcs_len
from .models import (
    LLM, MATCHMAKING_COOLDOWN, MAX_WARRIOR_LENGTH, Arena, Battle, Game,
    WarriorArena,
)
from .openai import openai_client, resolve_battle_openai


logger = logging.getLogger(__name__)


def do_moderation(goal, warrior_id):
    now = timezone.now()
    warrior = WarriorArena.objects.get(id=warrior_id)
    assert warrior.moderation_date is None
    moderation_results = openai_client.moderations.create(
        input='\n'.join([
            warrior.name,
            warrior.author_name,
            warrior.body,
        ]),
    )
    (result,) = moderation_results.results
    warrior.moderation_passed = not result.flagged
    warrior.moderation_model = moderation_results.model
    warrior.moderation_date = now
    warrior.save(update_fields=[
        'moderation_passed',
        'moderation_model',
        'moderation_date',
    ])
    return AllDone()


def schedule_battles(n=10, now=None):
    for _ in range(n):
        schedule_battle(now=now)


@transaction.atomic
def schedule_battle(now=None):
    if now is None:
        now = timezone.now()
    warrior = WarriorArena.objects.battleworthy().filter(
        next_battle_schedule__lte=now,
    ).order_by('next_battle_schedule').select_for_update(
        no_key=True,
        skip_locked=True,
    ).first()
    if warrior is None:
        return
    opponent = warrior.find_opponent()
    if opponent is None:
        warrior.next_battle_schedule = now + warrior.get_next_battle_delay() + datetime.timedelta(minutes=1)
        warrior.save(update_fields=['next_battle_schedule'])
        return
    warrior.create_battle(opponent, now=now)


def schedule_battles_top():
    for arena in Arena.objects.all():
        schedule_battle_top_arena(arena.id)


def schedule_battle_top_arena(arena_id):
    rating = 4000  # arbitrary value, higer than any real rating
    warriors_above = set()
    while True:
        with transaction.atomic():
            warrior = WarriorArena.objects.battleworthy().filter(
                arena_id=arena_id,
                rating__lt=rating,
            ).order_by('-rating').select_for_update(
                no_key=True,
                skip_locked=True,
            ).first()
            if warrior is None:
                # we are at the bottom of the ranking
                return None
            rating = warrior.rating
            if warrior.id in warriors_above:
                # may happen becuase of concurrent updates, just skip
                continue
            warriors_above.add(warrior.id)
            if random.random() < 0.9:
                # warrior gets picked only ocasionally
                continue

            # try find and opponent among the warriors above
            historic_battles = Battle.objects.with_warrior(warrior).filter(
                scheduled_at__gt=timezone.now() - MATCHMAKING_COOLDOWN,
            )
            opponent = WarriorArena.objects.filter(
                id__in=warriors_above,
            ).exclude(
                id=warrior.id,
            ).exclude(
                id__in=historic_battles.values('warrior_1'),
            ).exclude(
                id__in=historic_battles.values('warrior_2'),
            ).order_by('rating').first()

            if opponent is not None:
                return warrior.create_battle(opponent)


def resolve_battle_1_2(goal, battle_id):
    return resolve_battle(battle_id, '1_2')


def resolve_battle_2_1(goal, battle_id):
    return resolve_battle(battle_id, '2_1')


def resolve_battle(battle_id, direction):
    now = timezone.now()
    battle = Battle.objects.filter(id=battle_id).select_related(
        'arena',
        'warrior_1',
        'warrior_2',
    ).get()
    battle_view = Game(battle, direction)

    if battle_view.resolved_at is not None:
        logger.error('Battle already resolved %s, %s', battle_id, direction)
        return AllDone()

    resolve_battle_function = {
        LLM.GPT_3_5_TURBO: resolve_battle_openai,
        LLM.OPENAI_GPT: resolve_battle_openai,
        LLM.CLAUDE_3_HAIKU: anthropic.resolve_battle,
    }[battle_view.arena.llm]

    try:
        (
            result,
            finish_reason,
            llm_version,
        ) = resolve_battle_function(
            battle_view.warrior_1.body,
            battle_view.warrior_2.body,
            battle_view.arena.prompt,
        )
    except RateLimitError:
        logger.exception('LLM API rate limit')
        # try again in some time
        return RetryMeLater(precondition_date=now + datetime.timedelta(minutes=5))
    else:
        battle_view.result = result[:MAX_WARRIOR_LENGTH]
        battle_view.lcs_len_1 = lcs_len(battle_view.warrior_1.body, battle_view.result)
        battle_view.lcs_len_2 = lcs_len(battle_view.warrior_2.body, battle_view.result)
        battle_view.finish_reason = finish_reason
        # but the API finish reason doesn't matter if we cut the response
        if len(result) > MAX_WARRIOR_LENGTH:
            battle_view.finish_reason = 'character_limit'
        battle_view.llm_version = llm_version

    battle_view.resolved_at = now
    battle_view.save(update_fields=[
        'result',
        'lcs_len_1',
        'lcs_len_2',
        'finish_reason',
        'llm_version',
        'resolved_at',
    ])
    return AllDone()


def transfer_rating(goal, battle_id):
    battle = Battle.objects.filter(id=battle_id).select_related(
        'warrior_1',
        'warrior_2',
    ).get()
    battle.warrior_1.update_rating()
    battle.warrior_2.refresh_from_db()
    battle.warrior_2.update_rating()
    return AllDone()


def update_rating(n=10):
    errors = []
    for _ in range(n):
        with transaction.atomic():
            warrior = WarriorArena.objects.order_by(Abs('rating_error').desc()).select_for_update(
                no_key=True,
                skip_locked=True,
            ).first()
            if warrior is None:
                return
            error = warrior.update_rating()
            errors.append(error)
    return max(abs(e) for e in errors) if errors else 0
