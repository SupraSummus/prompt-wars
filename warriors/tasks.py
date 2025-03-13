import datetime
import logging
import random

from django.db import transaction
from django.utils import timezone
from django_goals.models import AllDone, RetryMeLater, schedule

from .battles import LLM, MATCHMAKING_COOLDOWN, Battle, Game
from .lcs import lcs_len
from .llms import anthropic
from .llms.exceptions import TransientLLMError
from .llms.google import resolve_battle_google
from .llms.openai import openai_client, resolve_battle_openai
from .models import Arena, WarriorArena, get_or_create_warrior_arenas
from .random_matchmaking import create_battle
from .score import ScoreAlgorithm, get_or_create_game_score
from .text_unit import TextUnit
from .warriors import MAX_WARRIOR_LENGTH, Warrior, ensure_name_generated


logger = logging.getLogger(__name__)


def do_moderation(goal, warrior_id):
    now = timezone.now()
    warrior = Warrior.objects.get(id=warrior_id)
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
    schedule(ensure_name_generated, args=[str(warrior_id)])
    warrior.schedule_voyage_3_embedding()
    return AllDone()


def schedule_battles_top(now=None):
    for arena in Arena.objects.filter(
        enabled=True,
    ):
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
            historic_battles = Battle.objects.with_warrior_arena(warrior).filter(
                scheduled_at__gt=timezone.now() - MATCHMAKING_COOLDOWN,
            )
            opponent = WarriorArena.objects.filter(
                id__in=warriors_above,
            ).exclude(
                id=warrior.id,
            ).exclude(
                warrior_id__in=historic_battles.values('warrior_1'),
            ).exclude(
                warrior_id__in=historic_battles.values('warrior_2'),
            ).order_by('rating').first()

            if opponent is not None:
                return create_battle(warrior, opponent)


def resolve_battle_1_2(goal, battle_id):
    return resolve_battle(battle_id, '1_2')


def resolve_battle_2_1(goal, battle_id):
    return resolve_battle(battle_id, '2_1')


def resolve_battle(battle_id, direction):
    now = timezone.now()
    battle = Battle.objects.filter(id=battle_id).select_related(
        'warrior_1',
        'warrior_2',
    ).get()
    battle_view = Game(battle, direction)

    if battle_view.resolved_at is None:
        r = _run_llm(battle_view, now)
        if isinstance(r, RetryMeLater):
            return r
        else:
            assert r is None
            assert battle_view.resolved_at is not None
            return RetryMeLater(message='Ran LLM')

    score_lcs = get_or_create_game_score(battle, direction, ScoreAlgorithm.LCS)
    score_embedings = get_or_create_game_score(battle, direction, ScoreAlgorithm.EMBEDDINGS)
    missing_scores = [
        score for score in [score_lcs, score_embedings]
        if not score.is_completed
    ]
    if missing_scores:
        return RetryMeLater(
            message='Need to wait for scores to be calculated',
            precondition_goals=[s.processed_goal for s in missing_scores],
        )

    return AllDone()


def _run_llm(battle_view, now):
    resolve_battle_function = {
        LLM.OPENAI_GPT: resolve_battle_openai,
        LLM.CLAUDE_3_HAIKU: anthropic.resolve_battle,
        LLM.GOOGLE_GEMINI: resolve_battle_google,
    }[battle_view.llm]

    try:
        (
            result,
            finish_reason,
            llm_version,
        ) = resolve_battle_function(
            battle_view.warrior_1.body,
            battle_view.warrior_2.body,
        )

    except TransientLLMError:
        logger.exception('Transient LLM error %s, %s', battle_view.battle.id, battle_view.direction)
        attempts = battle_view.attempts
        battle_view.attempts += 1
        battle_view.save(update_fields=['attempts'])
        if attempts < 6:
            # try again in some time
            exponent = attempts + random.random() - 0.5
            delay = datetime.timedelta(minutes=5) * 2**exponent
            return RetryMeLater(
                precondition_date=now + delay,
                message=f'Attempt {battle_view.attempts} - transient LLM error',
            )
        else:
            result = ''
            finish_reason = 'error'
            llm_version = ''

    battle_view.text_unit = TextUnit.get_or_create_by_content(result[:MAX_WARRIOR_LENGTH], now=now)
    battle_view.lcs_len_1 = lcs_len(battle_view.warrior_1.body, battle_view.result)
    battle_view.lcs_len_2 = lcs_len(battle_view.warrior_2.body, battle_view.result)
    battle_view.finish_reason = finish_reason
    # but the API finish reason doesn't matter if we cut the response
    if len(result) > MAX_WARRIOR_LENGTH:
        battle_view.finish_reason = 'character_limit'
    battle_view.llm_version = llm_version

    battle_view.resolved_at = now
    battle_view.save(update_fields=[
        'text_unit',
        'lcs_len_1',
        'lcs_len_2',
        'finish_reason',
        'llm_version',
        'resolved_at',
    ])


def transfer_rating(goal, battle_id):
    battle = Battle.objects.get(id=battle_id)
    for arena in Arena.objects.filter(llm=battle.llm):
        for warrior_arena in get_or_create_warrior_arenas(
            arena,
            [battle.warrior_1_id, battle.warrior_2_id],
        ).values():
            warrior_arena.update_rating()
    return AllDone()
