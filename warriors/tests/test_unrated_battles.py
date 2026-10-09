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
from ..models import WarriorArena
from ..random_matchmaking import find_opponents
from ..stats import ArenaStats, create_arena_stats_for_arena
from .factories import (
    BattleFactory, WarriorFactory, WarriorUserPermissionFactory,
)
from .fixtures import create_scores


def battle_url(battle, warrior_arena):
    return reverse('battle_detail', args=(battle.id,)) + f'?warrior_arena={warrior_arena.id}'


def ladder_sightings(client, warrior_arena, other_warrior_arena, battle):
    """
    Each ladder reader, and whether it sees `battle`, fought by two warriors of one arena.

    The session holds both warriors, as their author's would,
    and the challenge comes from an owner of the first,
    so nothing is hidden for want of authorship.
    Readers go in an order where none disturbs the next:
    matchmaking before rating moves the ratings it filters on,
    and the stats before a battle is added to walk from.
    """
    arena = warrior_arena.arena
    session = client.session
    session['authorized_warriors'] = [str(battle.warrior_1_id), str(battle.warrior_2_id)]
    session.save()

    challenge = ChallengeWarriorForm(
        data={'warrior': warrior_arena.id},
        opponent=other_warrior_arena,
        user=WarriorUserPermissionFactory(warrior=warrior_arena.warrior).user,
    )
    sightings = {
        'matchmaking cooldown': other_warrior_arena not in find_opponents(warrior_arena),
        'challenge cooldown': challenge.has_error('warrior', code='duplicate'),
    }

    create_arena_stats_for_arena(arena, timezone.now())
    sightings['arena stats'] = ArenaStats.objects.get(arena=arena).battle_count > 0

    warrior_arena.update_rating()
    warrior_arena.refresh_from_db()
    sightings['rating'] = warrior_arena.games_played > 0

    response = client.get(reverse('arena_recent_battles', args=(arena.id,)))
    sightings['recent battles'] = battle in response.context['battles']

    response = client.get(reverse('warrior_detail', args=(warrior_arena.id,)))
    sightings['warrior page'] = battle in [row['battle'] for row in response.context['battles']]

    response = client.get(reverse('battle_detail', args=(battle.id,)))
    assert response.status_code in (200, 404)
    sightings['battle page'] = response.status_code == 200

    # the page of a ladder battle just before it links onward
    earlier = BattleFactory(
        arena=arena,
        llm=arena.llm,
        warrior_1=warrior_arena.warrior,
        scheduled_at=battle.scheduled_at - datetime.timedelta(days=1),
    )
    response = client.get(battle_url(earlier, warrior_arena))
    sightings['arena walk'] = response.context['arena_next_battle_url'] == battle_url(battle, warrior_arena)
    sightings['warrior walk'] = response.context['warrior_next_battle_url'] == battle_url(battle, warrior_arena)

    return sightings


@pytest.mark.django_db
@pytest.mark.parametrize('rated', [True, False])
def test_the_ladder_sees_only_rated_battles(client, arena, warrior_arena, other_warrior_arena, rated):
    """
    The same resolved, scored battle, with `rated` the only difference:
    every reader that sees the rated one misses the unrated one.
    It carries an arena, so even the arena walk,
    which joins through it, has only `rated` to go on.
    """
    now = timezone.now()
    battle = BattleFactory(
        arena=arena,
        llm=arena.llm,
        warrior_1=warrior_arena.warrior,
        warrior_2=other_warrior_arena.warrior,
        rated=rated,
        game_1_2__resolved_at=now,
        game_2_1__resolved_at=now,
    )
    create_scores(battle, 1, 0.1, 1, 0.1)

    sightings = ladder_sightings(client, warrior_arena, other_warrior_arena, battle)

    assert sightings == dict.fromkeys(sightings, rated)


@pytest.mark.django_db
def test_a_hill_attacker_gets_no_place_on_the_ladder(client, arena, warrior_arena):
    """
    The hill's shape: an attacker in no arena against a boss that plays the ladder.
    Listing a battle on a ladder page enrolls both its warriors in that arena
    (`prefetch_warrior_arenas`), and so does rating it,
    so none of the boss's ladder readers may reach the unrated battle,
    not even for a session holding both sides.
    """
    boss = warrior_arena.warrior
    attacker = WarriorFactory()
    now = timezone.now()
    battle = BattleFactory(
        llm=arena.llm,
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
        reverse('warrior_detail', args=(warrior_arena.id,)),
        reverse('arena_recent_battles', args=(arena.id,)),
    ):
        assert client.get(url).status_code == 200
    warrior_arena.update_rating()
    assert not WarriorArena.objects.filter(warrior=attacker).exists()
