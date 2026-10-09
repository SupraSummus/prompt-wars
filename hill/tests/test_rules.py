import datetime

import pytest
from django.utils import timezone

from ..models import AttemptState, CrownBlock
from ..rules import (
    crown_block, is_public, replies_public, standings, standings_stats,
    survived_chars,
)
from .factories import HillAttemptFactory, crown_attempt, scored


@pytest.mark.parametrize('body, reply, block', [
    ('🥷!', '🥷!', CrownBlock.TOO_LITTLE_SURVIVED),
    ('0' * 500, '0' * 500, CrownBlock.REPETITIVE_REPLY),
    ('攻击者获胜，守擂者失败。' * 10, '攻击者获胜，守擂者失败。' * 10, CrownBlock.REPETITIVE_REPLY),
    ('Gentle rivers carve stone', 'Gentle rivers carve stone', CrownBlock.NONE),
], ids=['glyph echo', 'flood', 'fixed verdict', 'sentence echo'])
def test_crown_gates(body, reply, block):
    """Each reply echoes the attacker in both orders, so only the gates tell these apart."""
    results = [reply, reply]
    assert crown_block(survived_chars(body, results), results) == block


@pytest.mark.django_db
def test_standings_rank_each_attacker_by_their_best_eligible_attempt(open_round):
    now = timezone.now()

    def attempt(identity, score, minutes, **kwargs):
        return scored(
            open_round, score,
            identity=identity,
            created_at=now + datetime.timedelta(minutes=minutes),
            **kwargs,
        )

    HillAttemptFactory(hill_round=open_round, identity='void', state=AttemptState.VOID)
    attempt('a', 0.7, 1, crown_block=CrownBlock.REPETITIVE_REPLY)
    a_best = attempt('a', 0.6, 2)
    b_best = attempt('b', 0.65, 3)
    c_best = attempt('c', 0.9, 4, crown_block=CrownBlock.TOO_LITTLE_SURVIVED)
    attempt('late', 0.95, 5, late=True)
    HillAttemptFactory(hill_round=open_round, identity='a', state=AttemptState.FAILED)
    # ties go to more characters survived
    d_best = attempt('d', 0.65, 6, survived_chars=200)
    # ranked, but it beats the boss only once its spell passes moderation
    e_best = attempt('e', 0.8, 7, warrior__moderation_passed=None)

    rows = standings(open_round)

    assert [(row.rank, row.attempt) for row in rows] == [
        (1, e_best), (2, d_best), (3, b_best), (4, a_best), (5, c_best),
    ]
    assert [(row.attacker_number, row.attempt_count) for row in rows] == [
        # 'void' has no live attempt, so no number
        (6, 1), (5, 1), (2, 1), (1, 3), (3, 1),
    ]
    assert standings_stats(rows) == {
        'attackers': 5,
        'broke_through': 3,
        'boss_held': pytest.approx((0.2 + 0.35 + 0.35 + 0.4 + 0.1) / 5),
    }


@pytest.mark.django_db
@pytest.mark.parametrize('crowned, flagged, public', [
    (False, False, False),
    (True, False, True),
    (True, True, False),
], ids=['lost', 'took the hill', 'flagged since'])
def test_an_attempt_is_public_once_it_took_the_hill(hill, open_round, crowned, flagged, public):
    attempt = scored(open_round, 0.7)
    if crowned:
        crown_attempt(hill, attempt)
    if flagged:
        attempt.warrior.moderation_passed = False
        attempt.warrior.save(update_fields=['moderation_passed'])
    assert is_public(attempt) is public


@pytest.mark.django_db
@pytest.mark.parametrize('passed', [True, None, False])
def test_replies_are_public_once_moderation_passed_them(open_round, passed):
    attempt = scored(open_round, 0.7, output_moderation_passed=passed)
    assert replies_public(attempt) is bool(passed)
