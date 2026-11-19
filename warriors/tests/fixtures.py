from unittest import mock

import pytest
from django.utils import timezone

from .. import embeddings
from ..score import ScoreAlgorithm
from .factories import (
    BattleFactory, GameScoreFactory, WarriorFactory, WarriorRatingFactory,
    WarriorUserPermissionFactory, game_of,
)


@pytest.fixture
def warrior(request):
    return WarriorFactory(
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def warrior_rating(request, warrior):
    """The warrior's rating in `Ranking.LCS`, the factory's default ranking."""
    return WarriorRatingFactory(
        warrior=warrior,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def warrior_user_permission(request, warrior, user):
    return WarriorUserPermissionFactory(
        warrior=warrior,
        user=user,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def other_warrior(request):
    return WarriorFactory(
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def other_warrior_rating(request, other_warrior):
    return WarriorRatingFactory(
        warrior=other_warrior,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def battle(
    request,
    warrior, other_warrior,
):
    return BattleFactory(
        warrior_1=warrior,
        warrior_2=other_warrior,
        **getattr(request, 'param', {}),
    )


@pytest.fixture
def resolved_battle(
    request,
    warrior, other_warrior,
):
    now = timezone.now()
    battle = BattleFactory(
        warrior_1=warrior,
        warrior_2=other_warrior,
        game_1_2__resolved_at=now,
        game_2_1__resolved_at=now,
        **getattr(request, 'param', {}),
    )
    create_scores(battle, 1, 0.1, 1, 0.1)
    return battle


@pytest.fixture
def gemini(monkeypatch):
    """The mocked Gemini call, its return value `(reply, finish_reason, version)`; embeddings stubbed out."""
    reply = mock.MagicMock(return_value=('', 'STOP', 'gemini-test'))
    monkeypatch.setattr('warriors.tasks.resolve_battle_google', reply)
    monkeypatch.setattr(embeddings, 'get_embedding', mock.MagicMock(return_value=[0.0] * 1024))
    return reply


def create_scores(
    battle, score_1_2_1, score_1_2_2, score_2_1_1, score_2_1_2,
    algorithm=ScoreAlgorithm.LCS,
):
    GameScoreFactory(
        game=game_of(battle, '1_2'),
        algorithm=algorithm,
        warrior_1_similarity=score_1_2_1,
        warrior_2_similarity=score_1_2_2,
    )
    GameScoreFactory(
        game=game_of(battle, '2_1'),
        algorithm=algorithm,
        # in the game order "battle-level warrior 2" is the first one
        warrior_1_similarity=score_2_1_2,
        warrior_2_similarity=score_2_1_1,
    )
