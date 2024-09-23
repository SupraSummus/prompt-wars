import pytest
from django.urls import reverse
from django.utils import timezone
from django_goals.models import Goal

from users.tests.factories import UserFactory

from ..models import (
    MAX_WARRIOR_LENGTH, Battle, WarriorArena, WarriorUserPermission,
)


@pytest.mark.django_db
def test_arena_detail(client, arena):
    response = client.get(
        reverse('arena_detail', args=(arena.id,))
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_create_warrior_get(client, default_arena):
    response = client.get(reverse('warrior_create'))
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('has_authorized_warriors', [True, False])
def test_create_warrior(client, mocked_recaptcha, has_authorized_warriors, default_arena):
    if has_authorized_warriors:
        session = client.session
        session['authorized_warriors'] = []
        session.save()
    response = client.post(
        reverse('warrior_create'),
        data={
            'name': 'Test Warrior',
            'author_name': 'Test Author',
            'body': 'Test Body',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302, response.context['form'].errors
    path = response.url
    warrior_id = path.split('/')[-2]

    # right database state
    warrior = WarriorArena.objects.get(id=warrior_id)
    assert warrior.arena == default_arena
    assert warrior.name == 'Test Warrior'
    assert warrior.author_name == 'Test Author'
    assert warrior.body == 'Test Body'
    assert len(warrior.body_sha_256) == 32
    assert warrior.rating == 0.0
    assert warrior.games_played == 0
    assert warrior.next_battle_schedule is None
    assert warrior.moderation_date is None

    # moderation task scheduled
    goal = Goal.objects.get()
    assert goal.handler == 'warriors.tasks.do_moderation'
    assert goal.instructions['args'] == [str(warrior.id)]

    # session is athorized for new warrior
    assert str(warrior.id) in response.client.session['authorized_warriors']


@pytest.mark.django_db
def test_create_warrior_arena(client, mocked_recaptcha, arena):
    response = client.post(
        reverse('arena_warrior_create', args=(arena.id,)),
        data={
            'body': 'Test Warrior',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = WarriorArena.objects.get()
    assert warrior.arena == arena


@pytest.mark.django_db
def test_create_warrior_duplicate(client, warrior, mocked_recaptcha, default_arena):
    """
    It is not possible to create a warrior that has the same body as another.
    But we have a "discover" mechanics.
    """
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': warrior.body,
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior_id = response.url.split('/')[-2]
    assert warrior_id == str(warrior.id)
    assert str(warrior.id) in response.client.session['authorized_warriors']


@pytest.mark.django_db
def test_create_no_strip(client, mocked_recaptcha, default_arena):
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': ' Test \r\nWarrior \n\n',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = WarriorArena.objects.get()
    assert warrior.body == ' Test \nWarrior \n\n'


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('length', 'expect_success'),
    [
        (MAX_WARRIOR_LENGTH, True),
        (MAX_WARRIOR_LENGTH + 1, False),
    ],
)
def test_create_crlf_length(client, mocked_recaptcha, default_arena, length, expect_success):
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': '\r\n' * length,
            'g-recaptcha-response': 'PASSED',
        },
    )
    if expect_success:
        assert response.status_code == 302
        warrior = WarriorArena.objects.get()
        assert warrior.body == '\n' * length
    else:
        assert response.status_code == 200
        assert response.context['form'].errors['body']


@pytest.mark.django_db
def test_create_authenticated(user, user_client, mocked_recaptcha, default_arena):
    response = user_client.post(
        reverse('warrior_create'),
        data={
            'body': 'Test Warrior',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = WarriorArena.objects.get()
    assert warrior.created_by == user
    assert user in warrior.users.all()


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'name': 'strongest',
    'public_battle_results': False,
}], indirect=True)
def test_create_authenticated_duplicate(user, user_client, warrior, mocked_recaptcha, default_arena):
    response = user_client.post(
        reverse('warrior_create'),
        data={
            'body': warrior.body,
            'name': 'surely a duplicate',
            'public_battle_results': True,
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior_id = response.url.split('/')[-2]
    assert warrior_id == str(warrior.id)

    # name is not changed
    warrior.refresh_from_db()
    assert warrior.name == 'strongest'

    # at least one user marked battles as public, so the warrior have public battles
    assert warrior.public_battle_results is True

    # user has access to the warrior
    warrior_user_permission = WarriorUserPermission.objects.get(
        warrior_arena=warrior,
        user=user,
    )
    assert warrior_user_permission.name == 'surely a duplicate'


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
def test_warrior_details(client, warrior, battle):
    response = client.get(
        reverse('warrior_detail', args=(warrior.id,))
    )
    assert response.status_code == 200
    assert battle in response.context['battles']


@pytest.mark.django_db
@pytest.mark.parametrize('good_secret', [True, False])
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'lcs_len_1_2_1': 23,
    'lcs_len_1_2_2': 32,
}], indirect=True)
def test_warrior_details_secret(client, warrior, good_secret, battle):
    if good_secret:
        secret = warrior.secret
    else:
        secret = 'asdf'
    response = client.get(
        reverse('warrior_detail', args=(warrior.id,)) + '?secret=' + secret
    )
    assert response.status_code == 200
    assert response.context['show_secrets'] == good_secret
    assert (warrior.body in response.content.decode()) == good_secret


@pytest.mark.django_db
def test_warrior_details_creates_user_permission(user, user_client, warrior):
    assert user not in warrior.users.all()
    response = user_client.get(
        reverse('warrior_detail', args=(warrior.id,)) + '?secret=' + warrior.secret
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
def test_challenge_warrior_post(user_client, warrior, warrior_user_permission, other_warrior):
    response = user_client.post(
        reverse('challenge_warrior', args=(other_warrior.id,)),
        data={
            'warrior': warrior.id,
        },
    )
    assert response.status_code == 302
    assert Battle.objects.with_warriors(warrior, other_warrior).exists()


@pytest.mark.django_db
def test_challenge_warrior_post_duplicate(user_client, warrior, warrior_user_permission, other_warrior, battle):
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
@pytest.mark.parametrize('warrior', [
    {'public_battle_results': False},
    {'public_battle_results': True},
], indirect=True)
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'result_1_2': 'asdf1234',
}], indirect=True)
def test_battle_details_public(client, battle, warrior):
    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200
    assert ('asdf1234' in response.content.decode()) is warrior.public_battle_results


@pytest.mark.django_db
@pytest.mark.parametrize('battle', [{
    'resolved_at_1_2': timezone.now(),
    'result_1_2': '',
    'finish_reason_1_2': 'error',
}], indirect=True)
def test_battle_details_error(user_client, battle, warrior_user_permission):
    response = user_client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200
    game = response.context['battle'].game_1_2
    assert game.show_secrets_1 or game.show_secrets_2


@pytest.mark.django_db
def test_leaderboard(client, arena, settings, warrior, default_arena):
    response = client.get(reverse('warrior_leaderboard'))
    assert response.status_code == 200
    assert warrior in response.context['warriors']


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'next_battle_schedule': timezone.now()}], indirect=True)
def test_upcoming_battles(user_client, warrior, warrior_user_permission, default_arena):
    response = user_client.get(reverse('upcoming_battles'))
    assert response.status_code == 200
    assert warrior in response.context['warriors']


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
