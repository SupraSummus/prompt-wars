import datetime
import logging
import random
from hashlib import sha256

from django.db import transaction
from django.utils import timezone
from django_goals.models import AllDone, RetryMeLater, schedule

from .battles import LLM, Battle
from .llms import anthropic
from .llms.exceptions import TransientLLMError
from .llms.google import resolve_battle_google
from .llms.openai import openai_client, resolve_battle_openai
from .random_matchmaking import create_battle
from .rankings import Ranking
from .rating_models import WarriorRating
from .score import ScoreAlgorithm, get_or_create_game_score
from .text_unit import TextUnit
from .warriors import MAX_WARRIOR_LENGTH, Warrior, ensure_name_generated


logger = logging.getLogger(__name__)

# Transient LLM failures a game retries, backing off, before it resolves as an 'error'.
MAX_TRANSIENT_RETRIES = 6


def do_moderation(goal, warrior_id):
    now = timezone.now()
    warrior = Warrior.objects.get(id=warrior_id)
    assert warrior.moderation_date is None
    moderation_results = openai_client.moderations.create(
        model="omni-moderation-latest",
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


def schedule_battle_top(now=None, ranking=None):
    """
    A battle near the top of a ranking, drawn at random unless given:
    regular matchmaking pairs only by `LEADING_RANKING`,
    so this is where every leaderboard's leaders meet each other.
    Walking down from the best, a warrior picked now and then
    meets the lowest-rated of those above it it has not fought within the cooldown.
    """
    if ranking is None:
        ranking = random.choice(list(Ranking))
    rating = 4000  # arbitrary value, higer than any real rating
    ratings_above = set()
    while True:
        with transaction.atomic():
            warrior_rating = WarriorRating.objects.battleworthy().filter(
                ranking=ranking,
                rating__lt=rating,
            ).order_by('-rating').select_for_update(
                no_key=True,
                skip_locked=True,
            ).first()
            if warrior_rating is None:
                # we are at the bottom of the ranking
                return None
            rating = warrior_rating.rating
            if warrior_rating.id in ratings_above:
                # may happen becuase of concurrent updates, just skip
                continue
            ratings_above.add(warrior_rating.id)
            if random.random() < 0.9:
                # warrior gets picked only ocasionally
                continue

            # try find and opponent among the warriors above
            historic_battles = Battle.objects.with_warrior(warrior_rating.warrior_id).recent()
            opponent = WarriorRating.objects.filter(
                id__in=ratings_above,
            ).exclude(
                id=warrior_rating.id,
            ).exclude(
                warrior_id__in=historic_battles.values('warrior_1'),
            ).exclude(
                warrior_id__in=historic_battles.values('warrior_2'),
            ).order_by('rating').select_related('warrior').first()

            if opponent is not None:
                return create_battle(warrior_rating.warrior, opponent.warrior)


def resolve_battle_1_2(goal, battle_id):
    return resolve_battle(goal, battle_id, '1_2')


def resolve_battle_2_1(goal, battle_id):
    return resolve_battle(goal, battle_id, '2_1')


def resolve_battle(goal, battle_id, direction):
    now = timezone.now()
    battle = Battle.objects.get(id=battle_id)
    # A direction names the warrior that leads the prompt, and
    # Battle.create writes both games with the battle, so the
    # unique (battle, warrior_1) finds this one. processed_goal cannot:
    # backfilled rows have none, and goal collection clears the rest.
    leader_id, follower_id = battle.warrior_1_id, battle.warrior_2_id
    if direction == '2_1':
        leader_id, follower_id = follower_id, leader_id
    game = battle.games.select_related(
        'warrior_1',
        'warrior_2',
    ).get(warrior_1_id=leader_id)
    assert game.llm == battle.llm
    assert game.warrior_2_id == follower_id
    assert game.scheduled_at == battle.scheduled_at

    if game.resolved_at is None:
        r = _run_llm(game, now)
        if isinstance(r, RetryMeLater):
            return r
        else:
            assert r is None
            assert game.resolved_at is not None
            return RetryMeLater(message='Ran LLM')

    score_lcs = get_or_create_game_score(game, ScoreAlgorithm.LCS)
    score_embedings = get_or_create_game_score(game, ScoreAlgorithm.EMBEDDINGS)
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


def _run_llm(game, now):
    resolve_battle_function = {
        LLM.OPENAI_GPT: resolve_battle_openai,
        LLM.CLAUDE: anthropic.resolve_battle,
        LLM.GOOGLE_GEMINI: resolve_battle_google,
    }[game.llm]

    try:
        # Nothing but the two prompts ("What the model is" in CONCEPT.md).
        (
            result,
            finish_reason,
            llm_version,
        ) = resolve_battle_function(
            game.warrior_1.body,
            game.warrior_2.body,
        )

    except TransientLLMError:
        logger.exception('Transient LLM error, battle %s game %s', game.battle_id, game.id)
        attempts = game.attempts
        game.attempts += 1
        game.save(update_fields=['attempts'])

        if attempts < MAX_TRANSIENT_RETRIES:
            # try again in some time
            exponent = attempts + random.random() - 0.5
            delay = datetime.timedelta(minutes=5) * 2**exponent
            return RetryMeLater(
                precondition_date=now + delay,
                message=f'Attempt {game.attempts} - transient LLM error',
            )
        else:
            result = ''
            finish_reason = 'error'
            llm_version = ''

    game.input_sha256 = sha256(
        (game.warrior_1.body + game.warrior_2.body).encode('utf-8')
    ).digest()
    game.text_unit = TextUnit.get_or_create_by_content(result[:MAX_WARRIOR_LENGTH], now=now)
    game.finish_reason = finish_reason
    # but the API finish reason doesn't matter if we cut the response
    if len(result) > MAX_WARRIOR_LENGTH:
        game.finish_reason = 'character_limit'
    game.llm_version = llm_version

    game.resolved_at = now
    game.save(update_fields=[
        'input_sha256',
        'text_unit',
        'finish_reason',
        'llm_version',
        'resolved_at',
    ])


def transfer_rating(goal, battle_id):
    # Every ranking reads every battle, so each refits both warriors.
    battle = Battle.objects.get(id=battle_id)
    for warrior_rating in WarriorRating.objects.filter(
        warrior_id__in=[battle.warrior_1_id, battle.warrior_2_id],
    ).order_by('ranking', 'id'):
        warrior_rating.update_rating()
    return AllDone()
