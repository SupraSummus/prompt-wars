import pytest
from django.urls import reverse
from django.utils import timezone

from users.tests.factories import UserFactory

from ..models import Battle
from ..text_unit import TextUnit
from .factories import BattleFactory, TextUnitFactory, WarriorArenaFactory


@pytest.mark.django_db
def test_arena_detail(client, arena):
    response = client.get(
        reverse('arena_detail', args=(arena.id,))
    )
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [
    {'moderation_passed': False},
    {'moderation_passed': True},
    {'moderation_passed': None},
], indirect=True)
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'lcs_len_1_2_1': 23,
    'lcs_len_1_2_2': 32,
}], indirect=True)
def test_warrior_details(client, warrior_arena, battle):
    response = client.get(
        reverse('warrior_detail', args=(warrior_arena.id,))
    )
    assert response.status_code == 200
    assert battle.get_warrior_viewpoint(warrior_arena) in response.context['battles']


@pytest.mark.django_db
def test_warrior_details_creates_user_permission(user, user_client, warrior_arena, warrior):
    assert user not in warrior.users.all()
    session = user_client.session
    session['authorized_warriors'] = [str(warrior.id)]
    session.save()
    response = user_client.get(
        reverse('warrior_detail', args=(warrior_arena.id,)),
    )
    assert response.status_code == 200
    assert user in warrior.users.all()


@pytest.mark.django_db
@pytest.mark.parametrize('session_authorized', [True, False])
def test_warrior_details_authorized_session(client, warrior, warrior_arena, session_authorized):
    session = client.session
    session['authorized_warriors'] = [str(warrior.id)] if session_authorized else []
    session.save()
    response = client.get(
        reverse('warrior_detail', args=(warrior_arena.id,))
    )
    assert response.status_code == 200
    assert response.context['show_secrets'] == session_authorized
    assert (warrior_arena.body in response.content.decode()) == session_authorized


@pytest.mark.django_db
def test_warrior_details_do_few_sql_queries(client, arena, warrior_arena, django_assert_max_num_queries):
    n = 100
    for _ in range(n):
        other_warrior_arena = WarriorArenaFactory(arena=arena)
        battle_warrior_1 = warrior_arena.warrior
        battle_warrior_2 = other_warrior_arena.warrior
        if battle_warrior_1.id > battle_warrior_2.id:
            battle_warrior_1, battle_warrior_2 = battle_warrior_2, battle_warrior_1
        BattleFactory(
            arena=arena,
            warrior_1=battle_warrior_1,
            warrior_2=battle_warrior_2,
            resolved_at_1_2=timezone.now(),
            text_unit_1_2=TextUnitFactory(),
            resolved_at_2_1=timezone.now(),
            text_unit_2_1=TextUnitFactory(),
        )
    with django_assert_max_num_queries(n // 2):
        client.get(
            reverse('warrior_detail', args=(warrior_arena.id,))
        )


@pytest.mark.django_db
def test_warrior_set_public_battle_results(user_client, warrior, warrior_arena, warrior_user_permission):
    assert warrior.public_battle_results is False
    assert warrior_user_permission.public_battle_results is False
    response = user_client.post(
        reverse('warrior_set_public_battles', args=(warrior_arena.id,)),
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
def test_challenge_warrior_get(user_client, warrior_arena, warrior_user_permission, other_warrior_arena):
    response = user_client.get(
        reverse('challenge_warrior', args=(other_warrior_arena.id,))
    )
    assert response.status_code == 200
    assert warrior_arena in response.context['form'].fields['warrior'].queryset


@pytest.mark.django_db
def test_challenge_warrior_post(user_client, warrior_arena, warrior_user_permission, other_warrior_arena):
    response = user_client.post(
        reverse('challenge_warrior', args=(other_warrior_arena.id,)),
        data={
            'warrior': warrior_arena.id,
        },
    )
    assert response.status_code == 302
    assert Battle.objects.with_warrior_arenas(warrior_arena, other_warrior_arena).exists()


@pytest.mark.django_db
def test_challenge_warrior_post_duplicate(
    user_client, warrior_arena, warrior_user_permission, other_warrior_arena, battle,
):
    response = user_client.post(
        reverse('challenge_warrior', args=(other_warrior_arena.id,)),
        data={
            'warrior': warrior_arena.id,
        },
    )
    assert response.status_code == 200
    assert 'already happened' in response.context['form'].errors['warrior'][0]


@pytest.mark.django_db
def test_challenge_warrior_bad_data(user_client, warrior_arena):
    response = user_client.post(
        reverse('challenge_warrior', args=(warrior_arena.id,)),
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
@pytest.mark.parametrize('warrior', [
    {'public_battle_results': False},
    {'public_battle_results': True},
], indirect=True)
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
}], indirect=True)
def test_battle_details_public(client, battle, warrior_arena):
    battle.text_unit_1_2 = TextUnit.get_or_create_by_content('asdf1234')
    battle.save()
    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200
    assert ('asdf1234' in response.content.decode()) is warrior_arena.public_battle_results


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'finish_reason_1_2': 'error',
}], indirect=True)
def test_battle_details_error(user_client, battle, warrior_user_permission):
    assert battle.text_unit_1_2 is None
    response = user_client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200
    game = response.context['battle'].game_1_2
    assert game.show_secrets_1 or game.show_secrets_2


@pytest.mark.django_db
def test_leaderboard(client, arena, settings, warrior_arena, default_arena):
    response = client.get(reverse('warrior_leaderboard'))
    assert response.status_code == 200
    assert warrior_arena in response.context['warriors']


@pytest.mark.django_db
@pytest.mark.parametrize('warrior_arena', [{'next_battle_schedule': timezone.now()}], indirect=True)
def test_upcoming_battles(user_client, warrior_arena, warrior_user_permission, default_arena):
    response = user_client.get(reverse('upcoming_battles'))
    assert response.status_code == 200
    assert warrior_arena in response.context['warriors']


@pytest.mark.django_db
def test_recent_battles(user_client, battle, warrior_user_permission, default_arena):
    response = user_client.get(reverse('recent_battles'))
    assert response.status_code == 200
    assert battle in response.context['battles']


@pytest.mark.django_db
def test_recent_battles_no_duplicates(user, user_client, battle, default_arena):
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
