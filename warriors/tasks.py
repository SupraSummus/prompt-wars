import logging
import random

import openai
from django.conf import settings
from django.contrib.postgres.functions import TransactionNow
from django.db import transaction
from django.utils import timezone

from .lcs import lcs_len
from .models import (
    MATCHMAKING_COOLDOWN, MAX_WARRIOR_LENGTH, Battle, Game, Warrior,
)


logger = logging.getLogger(__name__)

openai_client = openai.Client(
    api_key=settings.OPENAI_API_KEY,
)


def do_moderation(warrior_id):
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
    warrior.next_battle_schedule = None if result.flagged else now
    warrior.save(update_fields=[
        'moderation_passed',
        'moderation_model',
        'moderation_date',
        'next_battle_schedule',
    ])


def schedule_battles(n=10, now=None):
    for _ in range(n):
        schedule_battle(now=now)


@transaction.atomic
def schedule_battle(now=None):
    if now is None:
        now = timezone.now()
    warrior = Warrior.objects.filter(
        next_battle_schedule__lte=now,
    ).order_by('next_battle_schedule').select_for_update(
        no_key=True,
        skip_locked=True,
    ).first()
    if warrior is None:
        return
    warrior.schedule_battle(now=now)


def schedule_battle_top():
    rating = 4000  # arbitrary value, higer than any real rating
    warriors_above = set()
    while True:
        with transaction.atomic():
            warrior = Warrior.objects.battleworthy().filter(
                arena_id=settings.DEFAULT_ARENA_ID,
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
            opponent = Warrior.objects.filter(
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
        return

    messages = []
    if battle_view.arena.prompt:
        messages.append({'role': 'system', 'content': battle_view.arena.prompt})
    messages.append({
        'role': 'user',
        'content': battle_view.warrior_1.body + battle_view.warrior_2.body,
    })
    try:
        response = openai_client.chat.completions.create(
            messages=messages,
            model='gpt-3.5-turbo',
            temperature=0,
            # Completion length limit is in tokens, so when measured in chars we will likely get more.
            # Other way arund is I think possible also - exotic unicode symbols
            # may be multiple LLM tokens, but a single char.
            # But this is a marginal case, so lets forget it for now.
            max_tokens=MAX_WARRIOR_LENGTH,
        )
    except openai.APIStatusError:
        logger.exception('OpenAI API call failed')
        battle_view.finish_reason = 'error'
    else:
        (resp_choice,) = response.choices
        result = resp_choice.message.content
        battle_view.result = result[:MAX_WARRIOR_LENGTH]
        battle_view.lcs_len_1 = lcs_len(battle_view.warrior_1.body, battle_view.result)
        battle_view.lcs_len_2 = lcs_len(battle_view.warrior_2.body, battle_view.result)
        battle_view.finish_reason = resp_choice.finish_reason
        # but the API finish reason doesn't matter if we cut the response
        if len(result) > MAX_WARRIOR_LENGTH:
            battle_view.finish_reason = 'character_limit'
        battle_view.llm_version = response.model + '/' + (response.system_fingerprint or '')

    battle_view.resolved_at = now
    battle_view.save(update_fields=[
        'result',
        'lcs_len_1',
        'lcs_len_2',
        'finish_reason',
        'llm_version',
        'resolved_at',
    ])


@transaction.atomic
def transfer_rating(battle_id):
    battle = Battle.objects.filter(id=battle_id).select_related(
        'warrior_1',
        'warrior_2',
    ).select_for_update(no_key=True).get()

    if battle.rating_transferred_at is not None:
        logger.error('Rating already transferred for battle %s', battle_id)
        return

    assert battle.resolved_at_1_2 is not None
    assert battle.resolved_at_2_1 is not None

    battle.rating_transferred_at = TransactionNow()
    battle.save(update_fields=[
        'rating_transferred_at',
    ])

    battle.warrior_1.update_rating()
    battle.warrior_2.refresh_from_db()
    battle.warrior_2.update_rating()
    battle.warrior_1.next_battle_schedule = TransactionNow() + battle.warrior_1.get_next_battle_delay()
    battle.warrior_2.next_battle_schedule = TransactionNow() + battle.warrior_2.get_next_battle_delay()
    Warrior.objects.bulk_update(
        [battle.warrior_1, battle.warrior_2],
        [
            'next_battle_schedule',
        ],
    )


def update_rating(n=10):
    errors = []
    for _ in range(n):
        with transaction.atomic():
            warrior = Warrior.objects.filter(
                rating_error__gt=0,
            ).order_by('-rating_error').first()
            if warrior is None:
                return
            error = warrior.update_rating()
            errors.append(error)
    return max(abs(e) for e in errors) if errors else 0
