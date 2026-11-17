"""
An unrated battle is played and scored like any other,
and the ladder never sees it.
"""
import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from ..battles import Battle
from ..forms import ChallengeWarriorForm
from ..random_matchmaking import find_opponents
from ..rankings import Ranking
from ..stats import RankingStats, create_ranking_stats_for
from .factories import (
    BattleFactory, WarriorFactory, WarriorUserPermissionFactory,
)
from .fixtures import create_scores


def battle_url(battle, warrior):
    return reverse('battle_detail', args=(battle.id,)) + f'?warrior={warrior.id}'


def ladder_sightings(client, warrior_rating, other_warrior_rating, battle):
    """
    Each ladder reader, and whether it sees `battle`, fought by two ladder warriors.

    The session holds both warriors, as their author's would,
    and the challenge comes from an owner of the first,
    so nothing is hidden for want of authorship.
    Readers go in an order where none disturbs the next:
    matchmaking before rating moves the ratings it filters on,
    and the stats before a battle is added to walk from.
    """
    warrior, other_warrior = warrior_rating.warrior, other_warrior_rating.warrior
    session = client.session
    session['authorized_warriors'] = [str(battle.warrior_1_id), str(battle.warrior_2_id)]
    session.save()

    challenge = ChallengeWarriorForm(
        data={'warrior': warrior.id},
        opponent=other_warrior,
        user=WarriorUserPermissionFactory(warrior=warrior).user,
    )
    sightings = {
        'matchmaking cooldown': other_warrior not in find_opponents(warrior),
        'challenge cooldown': challenge.has_error('warrior', code='duplicate'),
    }

    create_ranking_stats_for(Ranking.LCS, timezone.now())
    sightings['ranking stats'] = RankingStats.objects.get(ranking=Ranking.LCS).battle_count > 0

    warrior_rating.update_rating()
    warrior_rating.refresh_from_db()
    sightings['rating'] = warrior_rating.games_played > 0

    response = client.get(reverse('recent_battles'))
    sightings['recent battles'] = battle in response.context['battles']

    response = client.get(reverse('warrior_detail', args=(warrior.id,)))
    sightings['warrior page'] = battle in [row['battle'] for row in response.context['battles']]

    response = client.get(reverse('battle_detail', args=(battle.id,)))
    assert response.status_code in (200, 404)
    sightings['battle page'] = response.status_code == 200

    # the page of a ladder battle just before it links onward
    earlier = BattleFactory(
        warrior_1=warrior,
        scheduled_at=battle.scheduled_at - datetime.timedelta(days=1),
    )
    response = client.get(battle_url(earlier, warrior))
    sightings['ladder walk'] = response.context['ladder_next_battle_url'] == battle_url(battle, warrior)
    sightings['warrior walk'] = response.context['warrior_next_battle_url'] == battle_url(battle, warrior)

    return sightings


@pytest.mark.django_db
@pytest.mark.parametrize('rated', [True, False])
def test_the_ladder_sees_only_rated_battles(client, warrior_rating, other_warrior_rating, rated):
    """
    The same resolved, scored battle, with `rated` the only difference:
    every reader that sees the rated one misses the unrated one.
    """
    now = timezone.now()
    battle = BattleFactory(
        warrior_1=warrior_rating.warrior,
        warrior_2=other_warrior_rating.warrior,
        rated=rated,
        game_1_2__resolved_at=now,
        game_2_1__resolved_at=now,
    )
    create_scores(battle, 1, 0.1, 1, 0.1)

    sightings = ladder_sightings(client, warrior_rating, other_warrior_rating, battle)

    assert sightings == dict.fromkeys(sightings, rated)


@pytest.mark.django_db
def test_a_hill_attacker_gets_no_place_on_the_ladder(client, warrior_rating):
    """
    The hill's shape: an attacker off the ladder against a boss that plays it.
    Listing a battle on a ladder page gives both its warriors ratings
    (`prefetch_warrior_ratings`), and so does rating it,
    so none of the boss's ladder readers may reach the unrated battle,
    not even for a session holding both sides.
    """
    boss = warrior_rating.warrior
    attacker = WarriorFactory(next_battle_schedule=None)
    now = timezone.now()
    battle = BattleFactory(
        warrior_1=boss,
        warrior_2=attacker,
        rated=False,
        game_1_2__resolved_at=now,
        game_2_1__resolved_at=now,
    )
    create_scores(battle, 1, 0.1, 1, 0.1)

    assert Battle.objects.resolved().filter(id=battle.id).exists()
    session = client.session
    session['authorized_warriors'] = [str(boss.id), str(attacker.id)]
    session.save()
    for url in (
        reverse('warrior_detail', args=(boss.id,)),
        reverse('recent_battles'),
    ):
        assert client.get(url).status_code == 200
    warrior_rating.update_rating()
    assert not attacker.ratings.exists()
