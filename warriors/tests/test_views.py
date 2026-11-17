import datetime
import uuid

import pytest
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from users.tests.factories import UserFactory

from ..battles import Battle
from ..models import LegacyWarriorArena
from ..rankings import LEADING_RANKING, Ranking
from ..score import ScoreAlgorithm
from ..text_unit import TextUnit
from .factories import (
    BattleFactory, GameScoreFactory, WarriorFactory, WarriorRatingFactory,
    batch_create_battles, game_of,
)
from .fixtures import create_scores


@pytest.mark.parametrize(('arena_page', 'page'), [
    ('', reverse_lazy('home')),
    ('create/', reverse_lazy('warrior_create')),
    ('leaderboard/', reverse_lazy('warrior_leaderboard')),
    ('upcoming-battles/', reverse_lazy('upcoming_battles')),
    ('recent-battles/', reverse_lazy('recent_battles')),
])
def test_an_arena_page_leads_to_its_replacement(client, arena_page, page):
    response = client.get(f'/arena/{uuid.uuid4()}/{arena_page}')
    assert (response.status_code, response.url) == (301, str(page))


@pytest.mark.django_db
def test_a_warrior_arena_page_leads_to_its_warrior(client, warrior):
    legacy = LegacyWarriorArena.objects.create(id=uuid.uuid4(), warrior=warrior)
    response = client.get(f'/warrior-arena/{legacy.id}/')
    assert (response.status_code, response.url) == (301, warrior.get_absolute_url())
    assert client.get(f'/warrior-arena/{uuid.uuid4()}/').status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [
    {'moderation_passed': False},
    {'moderation_passed': True},
    {'moderation_passed': None},
], indirect=True)
@pytest.mark.parametrize('battle', [{
    'game_1_2__resolved_at': timezone.now(),
}], indirect=True)
def test_warrior_details(client, warrior, battle):
    response = client.get(
        reverse('warrior_detail', args=(warrior.id,))
    )
    assert response.status_code == 200
    assert battle in [row['battle'] for row in response.context['battles']]


@pytest.mark.django_db
def test_warrior_details_scores_belong_to_the_page_warrior(client):
    """
    The page's warrior leads one game and follows in the other,
    and both cells report that warrior's own score.
    Reaching for the battle's first warrior instead
    gives every number to the opponent, and nothing else looks wrong.
    """
    now = timezone.now()
    battle = BattleFactory(
        warrior_1__id=uuid.UUID(int=1),
        warrior_2__id=uuid.UUID(int=2),
        game_1_2__resolved_at=now,
        game_2_1__resolved_at=now,
    )
    create_scores(
        battle,
        score_1_2_1=0.1, score_1_2_2=0.2,
        score_2_1_1=0.3, score_2_1_2=0.4,
    )
    response = client.get(
        reverse('warrior_detail', args=(battle.warrior_2_id,))
    )

    row, = response.context['battles']
    assert [cell['game'].warrior_1_id for cell in row['games']] == [
        battle.warrior_2_id, battle.warrior_1_id,
    ]
    assert [cell['score'] for cell in row['games']] == [
        pytest.approx(0.4 / 0.7),  # leading, its own similarity is the larger
        pytest.approx(0.2 / 0.3),  # following, and still the larger
    ]


@pytest.mark.django_db
def test_warrior_details_creates_user_permission(user, user_client, warrior):
    assert user not in warrior.users.all()
    session = user_client.session
    session['authorized_warriors'] = [str(warrior.id)]
    session.save()
    response = user_client.get(
        reverse('warrior_detail', args=(warrior.id,)),
    )
    assert response.status_code == 200
    assert user in warrior.users.all()


@pytest.mark.django_db
@pytest.mark.parametrize('session_authorized', [True, False])
def test_warrior_details_authorized_session(client, warrior, session_authorized):
    session = client.session
    session['authorized_warriors'] = [str(warrior.id)] if session_authorized else []
    session.save()
    response = client.get(
        reverse('warrior_detail', args=(warrior.id,))
    )
    assert response.status_code == 200
    assert response.context['show_secrets'] == session_authorized
    assert (warrior.body in response.content.decode()) == session_authorized


@pytest.mark.django_db
def test_warrior_details_do_few_sql_queries(client, warrior, django_assert_max_num_queries):
    n = 100
    batch_create_battles(warrior, n)
    with django_assert_max_num_queries(n // 2):
        response = client.get(
            reverse('warrior_detail', args=(warrior.id,))
        )
    assert len(response.context['battles']) == n


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'next_battle_schedule': None}], indirect=True)
def test_warrior_details_of_a_warrior_off_the_ladder_write_nothing(client, warrior):
    """A hill attacker's page shows no rating, and viewing it creates none."""
    response = client.get(reverse('warrior_detail', args=(warrior.id,)))
    assert response.status_code == 200
    assert response.context['rating'] is None
    assert not warrior.ratings.exists()


@pytest.mark.django_db
@pytest.mark.parametrize('ranking', list(Ranking))
def test_warrior_details_read_battles_through_the_asked_ranking(client, warrior, ranking):
    """Every ranking's rating is on the page; the battle list reads through the one asked for."""
    WarriorRatingFactory(warrior=warrior, ranking=Ranking.SEMANTIC, rating=123)
    response = client.get(warrior.get_ranking_url(ranking))
    assert response.status_code == 200
    assert response.context['ranking'] == ranking
    assert response.context['rating'].ranking == ranking
    assert [row['ranking'] for row in response.context['ratings']] == list(Ranking)
    assert '123' in response.content.decode()


@pytest.mark.django_db
def test_warrior_set_public_battle_results(user_client, warrior, warrior_user_permission):
    assert warrior.public_battle_results is False
    assert warrior_user_permission.public_battle_results is False
    response = user_client.post(
        reverse('warrior_set_public_battles', args=(warrior.id,)),
        data={
            'public_battle_results': True,
        },
    )
    assert response.status_code == 302
    warrior.refresh_from_db()
    assert warrior.public_battle_results is True
    warrior_user_permission.refresh_from_db()
    assert warrior_user_permission.public_battle_results is True


@pytest.mark.django_db
def test_challenge_warrior_get(user_client, warrior, warrior_user_permission, other_warrior):
    response = user_client.get(
        reverse('challenge_warrior', args=(other_warrior.id,))
    )
    assert response.status_code == 200
    assert warrior in response.context['form'].fields['warrior'].queryset


@pytest.mark.django_db
@pytest.mark.parametrize('other_warrior', [{'next_battle_schedule': None}], indirect=True)
def test_challenge_a_warrior_off_the_ladder(user_client, warrior, warrior_user_permission, other_warrior):
    """A challenge is a ladder battle, and a hill attacker plays only the hill."""
    response = user_client.get(
        reverse('challenge_warrior', args=(other_warrior.id,))
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_challenge_warrior_post(user_client, warrior, warrior_user_permission, other_warrior):
    response = user_client.post(
        reverse('challenge_warrior', args=(other_warrior.id,)),
        data={
            'warrior': warrior.id,
        },
    )
    assert response.status_code == 302
    assert Battle.objects.with_warriors(warrior.id, other_warrior.id).exists()


@pytest.mark.django_db
def test_challenge_warrior_post_duplicate(
    user_client, warrior, warrior_user_permission, other_warrior, battle,
):
    response = user_client.post(
        reverse('challenge_warrior', args=(other_warrior.id,)),
        data={
            'warrior': warrior.id,
        },
    )
    assert response.status_code == 200
    assert 'already happened' in response.context['form'].errors['warrior'][0]


@pytest.mark.django_db
def test_challenge_warrior_bad_data(user_client, warrior):
    response = user_client.post(
        reverse('challenge_warrior', args=(warrior.id,)),
        data={},
    )
    assert response.status_code == 200
    assert 'warrior' in response.context['form'].errors


@pytest.mark.django_db
def test_battle_details(client, battle):
    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_battle_details_with_score(client, battle):
    """A game reports the algorithms that scored it, and nothing it lacks."""
    GameScoreFactory(
        game=game_of(battle, '1_2'),
        algorithm='lcs',
        warrior_1_similarity=0.5,
        warrior_2_similarity=0.5,
        warriors_similarity=0.5,
    )
    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200
    scored, unscored = response.context['game_blocks']
    assert [scoring['algorithm'] for scoring in scored['scorings']] == [
        ScoreAlgorithm.LCS.label,
    ]
    assert unscored['scorings'] == []


@pytest.mark.django_db
def test_battle_details_warrior_keeps_its_side(client, battle):
    """
    A game's header follows its prompt order,
    while its scores keep the battle's order, each warrior with its own number,
    so a warrior stays on one side of the page in both games.
    """
    create_scores(
        battle,
        score_1_2_1=0.1, score_1_2_2=0.2,
        score_2_1_1=0.3, score_2_1_2=0.4,
    )

    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )

    _, following = response.context['game_blocks']
    assert [entry['warrior'].id for entry in following['prompt_order']] == [
        battle.warrior_2_id, battle.warrior_1_id,
    ]
    scoring, = following['scorings']
    assert [(row['warrior'].id, row['side'], row['score']) for row in scoring['warriors']] == [
        (battle.warrior_1_id, 1, pytest.approx(0.3 / 0.7)),
        (battle.warrior_2_id, 2, pytest.approx(0.4 / 0.7)),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [
    {'public_battle_results': False},
    {'public_battle_results': True},
], indirect=True)
@pytest.mark.parametrize('battle', [{
    'game_1_2__resolved_at': timezone.now(),
}], indirect=True)
def test_battle_details_public(client, battle, warrior):
    game = game_of(battle, '1_2')
    game.text_unit = TextUnit.get_or_create_by_content('asdf1234')
    game.save(update_fields=['text_unit'])
    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200
    assert ('asdf1234' in response.content.decode()) is warrior.public_battle_results


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'game_1_2__resolved_at': timezone.now(),
    'game_1_2__finish_reason': 'error',
}], indirect=True)
def test_battle_details_error(user_client, battle, warrior_user_permission):
    """An errored game has no result text, and its author still gets the page."""
    assert game_of(battle, '1_2').text_unit is None
    # scoring an errored game leaves its row in place, with nothing in it
    GameScoreFactory(game=game_of(battle, '1_2'), algorithm=ScoreAlgorithm.LCS)
    response = user_client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200
    block = response.context['game_blocks'][0]
    assert block['game'].finish_reason == 'error'
    assert block['result_visible']
    scoring, = block['scorings']
    assert not scoring['scored']


def schedule_in_order(*battles):
    """Space battles a day apart, oldest first, so nav order is not left to chance."""
    now = timezone.now()
    for days, battle in enumerate(reversed(battles), start=1):
        battle.scheduled_at = now - datetime.timedelta(days=days)
        battle.save(update_fields=['scheduled_at'])


def battle_url(battle, warrior=None):
    url = reverse('battle_detail', args=(battle.id,))
    if warrior is not None:
        url += f'?warrior={warrior.id}'
    return url


@pytest.mark.django_db
def test_battle_details_nav_walks_both(client, warrior):
    """A battle of other warriors is the ladder's next one and not the warrior's."""
    older, middle, newer = batch_create_battles(warrior, 3)
    stranger = batch_create_battles(WarriorFactory(), 1)[0]
    schedule_in_order(older, middle, stranger, newer)

    response = client.get(battle_url(middle, warrior))

    assert response.status_code == 200
    assert response.context['ladder_previous_battle_url'] == battle_url(older, warrior)
    assert response.context['ladder_next_battle_url'] == battle_url(stranger, warrior)
    assert response.context['warrior_previous_battle_url'] == battle_url(older, warrior)
    assert response.context['warrior_next_battle_url'] == battle_url(newer, warrior)
    # both walks reach the page, not just the context
    content = response.content.decode()
    assert battle_url(stranger, warrior) in content
    assert battle_url(newer, warrior) in content


@pytest.mark.django_db
def test_battle_details_nav_without_a_warrior(client, warrior):
    """Naming no warrior leaves the ladder walk, so the battle URL stands alone."""
    older, middle, newer = batch_create_battles(warrior, 3)
    schedule_in_order(older, middle, newer)

    response = client.get(battle_url(middle))

    assert response.status_code == 200
    assert response.context['ladder_previous_battle_url'] == battle_url(older)
    assert response.context['ladder_next_battle_url'] == battle_url(newer)
    assert response.context['warrior_previous_battle_url'] is None
    assert response.context['warrior_next_battle_url'] is None


@pytest.mark.django_db
@pytest.mark.parametrize('bad_value', [
    lambda: 'not-a-uuid',
    lambda: str(uuid.uuid4()),
    lambda: str(WarriorFactory().id),
], ids=['malformed', 'unknown', 'stranger'])
def test_battle_details_nav_unrecognized_warrior(client, battle, bad_value):
    response = client.get(
        reverse('battle_detail', args=(battle.id,)),
        data={'warrior': bad_value()},
    )
    assert response.status_code == 200
    assert response.context['nav_warrior'] is None


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'game_1_2__resolved_at': timezone.now(),
}], indirect=True)
def test_warrior_details_links_carry_the_warrior(client, warrior, battle):
    response = client.get(
        reverse('warrior_detail', args=(warrior.id,))
    )
    assert battle_url(battle, warrior) in response.content.decode()


@pytest.mark.django_db
def test_leaderboard_opens_on_the_leading_ranking(client):
    response = client.get(reverse('warrior_leaderboard'))
    assert response.url == reverse('ranking_leaderboard', args=(LEADING_RANKING,))


@pytest.mark.django_db
@pytest.mark.parametrize('ranking', list(Ranking))
def test_leaderboard(client, ranking):
    mine = WarriorRatingFactory(ranking=ranking)
    other = WarriorRatingFactory(ranking=next(r for r in Ranking if r != ranking))
    response = client.get(reverse('ranking_leaderboard', args=(ranking,)))
    assert response.status_code == 200
    assert mine in response.context['ratings']
    assert other not in response.context['ratings']


def test_leaderboard_of_no_ranking(client):
    assert client.get(reverse('ranking_leaderboard', args=('no-such',))).status_code == 404


@pytest.mark.django_db
def test_loaderboard_sql_queries(client, django_assert_max_num_queries):
    n = 100
    WarriorRatingFactory.create_batch(n)
    with django_assert_max_num_queries(n // 2):
        response = client.get(reverse('ranking_leaderboard', args=(Ranking.LCS,)))
    assert response.context['ratings'].count() == n


@pytest.mark.django_db
def test_upcoming_battles(user_client, warrior, warrior_user_permission):
    response = user_client.get(reverse('upcoming_battles'))
    assert response.status_code == 200
    assert warrior in response.context['warriors']


@pytest.mark.django_db
def test_recent_battles(user_client, battle, warrior_user_permission):
    response = user_client.get(reverse('recent_battles'))
    assert response.status_code == 200
    assert battle in response.context['battles']


@pytest.mark.django_db
def test_recent_battles_no_duplicates(user, user_client, battle):
    # this user has access to both warriors
    battle.warrior_1.users.add(user)
    battle.warrior_2.users.add(user)
    # and there is another user with access to both warriors
    another_user = UserFactory()
    battle.warrior_1.users.add(another_user)
    battle.warrior_2.users.add(another_user)
    response = user_client.get(reverse('recent_battles'))
    assert response.status_code == 200
    assert len(response.context['battles']) == 1


@pytest.mark.django_db
@pytest.mark.parametrize('public_battle_results,expected_visible', [
    (True, True),
    (False, False),
])
def test_recent_battles_public_battle_results(
    client, battle,
    public_battle_results, expected_visible,
):
    """Test that battles are visible based on warrior's public_battle_results setting."""
    battle.warrior_1.public_battle_results = public_battle_results
    battle.warrior_1.save(update_fields=['public_battle_results'])

    response = client.get(reverse('recent_battles'))
    assert response.status_code == 200

    if expected_visible:
        assert battle in response.context['battles']
    else:
        assert battle not in response.context['battles']


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'moderation_passed': None}], indirect=True)
def test_a_fresh_warriors_page_polls_until_its_first_result(client, warrior):
    url = reverse('warrior_detail', args=(warrior.id,))
    assert 'hx-select="main"' in client.get(url).content.decode()
    assert client.get(url, {'polling': 'page'}).status_code == 204

    warrior.moderation_passed = True
    warrior.save(update_fields=['moderation_passed'])
    assert 'hx-select="#battles-section"' in client.get(url, {'polling': 'page'}).content.decode()
    assert client.get(url, {'polling': 'battles'}).status_code == 204

    batch_create_battles(warrior, 1)
    assert 'hx-get' not in client.get(url, {'polling': 'battles'}).content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'moderation_passed': None,
    'created_at': timezone.now() - datetime.timedelta(days=1),
}], indirect=True)
def test_warrior_details_of_an_old_warrior_do_not_poll(client, warrior):
    response = client.get(reverse('warrior_detail', args=(warrior.id,)))
    assert response.context['polling'] is None
