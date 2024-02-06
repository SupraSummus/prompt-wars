import openai
from django.conf import settings
from django.contrib.postgres.functions import TransactionNow
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import MAX_WARRIOR_LENGTH, Battle, BattleRelativeView, Warrior


openai_client = openai.Client(
    api_key=settings.OPENAI_API_KEY,
)


def resolve_battle(battle_id, direction):
    now = timezone.now()
    battle = Battle.objects.get(id=battle_id)
    battle_view = BattleRelativeView(battle, direction)
    assert battle_view.resolved_at is None

    prompt = battle.warrior_1.body + battle.warrior_2.body
    model = 'gpt-3.5-turbo'
    response = openai_client.chat.completions.create(
        messages=[
            {'role': 'user', 'message': prompt},
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
    battle_view.result = resp_choice.message[:MAX_WARRIOR_LENGTH]
    battle_view.llm_version = model + '/' + resp_choice.fingerprint

    battle_view.resolved_at = now
    battle_view.save(update_fields=[
        'result',
        'llm_version',
        'resolved_at',
    ])


@transaction.atomic
def transfer_rating(battle_id):
    battle = Battle.object.filter(id=battle_id).select_related(
        'warrior_1',
        'warrior_2',
    ).select_for_update(no_key=True).get()
    assert battle.rating_transferred_at is None
    Battle.object.filter(id=battle_id).update(
        rating_transferred_at=TransactionNow(),
    )
    rating_gained = battle.rating_gained
    Warrior.objects.filter(id=battle.warrior_1_id).update(
        rating=F('rating') + rating_gained,
    )
    Warrior.objects.filter(id=battle.warrior_2_id).update(
        rating=F('rating') - rating_gained,
    )


@transaction.atomic
def schedule_battles(n=10, now=None):
    if now is None:
        now = timezone.now()
    warriors = Warrior.objects.filter(
        next_battle_schedule__lte=now,
    ).order_by('next_battle_schedule').select_for_update(
        now_key=True,
        skip_locked=True,
    )[:n]
    for warrior in warriors:
        warrior.schedule_battle(now=now)
