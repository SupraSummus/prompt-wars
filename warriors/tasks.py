import openai
from django.conf import settings
from django.contrib.postgres.functions import TransactionNow
from django.db import transaction
from django.utils import timezone

from .lcs import lcs_len
from .models import MAX_WARRIOR_LENGTH, Battle, Game, Warrior


openai_client = openai.Client(
    api_key=settings.OPENAI_API_KEY,
)


def do_moderation(warrior_id):
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
    warrior.moderation_date = timezone.now()
    warrior.next_battle_schedule = None if result.flagged else '1970-01-01T00:00:00Z'
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


def resolve_battle(battle_id, direction):
    now = timezone.now()
    battle = Battle.objects.get(id=battle_id)
    battle_view = Game(battle, direction)
    assert battle_view.resolved_at is None

    prompt = battle_view.warrior_1.body + battle_view.warrior_2.body
    response = openai_client.chat.completions.create(
        messages=[
            {'role': 'user', 'content': prompt},
        ],
        model='gpt-3.5-turbo',
        temperature=0,
        # Completion length limit is in tokens, so when measured in chars we will likely get more.
        # Other way arund is I think possible also - exotic unicode symbols
        # may be multiple LLM tokens, but a single char.
        # But this is a marginal case, so lets forget it for now.
        max_tokens=MAX_WARRIOR_LENGTH,
    )
    (resp_choice,) = response.choices
    battle_view.result = resp_choice.message.content[:MAX_WARRIOR_LENGTH]
    battle_view.lcs_len_1 = lcs_len(battle_view.warrior_1.body, battle_view.result)
    battle_view.lcs_len_2 = lcs_len(battle_view.warrior_2.body, battle_view.result)
    battle_view.llm_version = response.model + '/' + (response.system_fingerprint or '')

    battle_view.resolved_at = now
    battle_view.save(update_fields=[
        'result',
        'lcs_len_1',
        'lcs_len_2',
        'llm_version',
        'resolved_at',
    ])


@transaction.atomic
def transfer_rating(battle_id):
    battle = Battle.objects.filter(id=battle_id).select_related(
        'warrior_1',
        'warrior_2',
    ).select_for_update(no_key=True).get()
    assert battle.rating_transferred_at is None
    assert battle.resolved_at_1_2 is not None
    assert battle.resolved_at_2_1 is not None

    battle.rating_transferred_at = TransactionNow()
    battle.save(update_fields=[
        'rating_transferred_at',
    ])

    battle.warrior_1.update_rating(save=False)
    battle.warrior_2.update_rating(save=False)
    battle.warrior_1.next_battle_schedule = TransactionNow() + battle.warrior_1.get_next_battle_delay()
    battle.warrior_2.next_battle_schedule = TransactionNow() + battle.warrior_2.get_next_battle_delay()
    Warrior.objects.bulk_update(
        [battle.warrior_1, battle.warrior_2],
        [
            'rating',
            'games_played',
            'next_battle_schedule',
        ],
    )
