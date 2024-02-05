import openai
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import MAX_WARRIOR_LENGTH, Battle, Warrior


openai_client = openai.Client(
    api_key=settings.OPENAI_API_KEY,
)


def resolve_battle(battle_id):
    now = timezone.now()
    battle = Battle.objects.get(id=battle_id)

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
    battle.result = resp_choice.message[:MAX_WARRIOR_LENGTH]
    battle.llm_version = model + '/' + resp_choice.fingerprint

    battle.resolved_at = now
    battle.save(update_fields=[
        'result',
        'llm_version',
        'resolved_at',
    ])

    rating_transfer = battle.rating_transfer
    with transaction.atomic():
        Warrior.objects.filter(id=battle.warrior_1_id).update(
            rating=F('rating') + rating_transfer,
        )
        Warrior.objects.filter(id=battle.warrior_2_id).update(
            rating=F('rating') - rating_transfer,
        )
