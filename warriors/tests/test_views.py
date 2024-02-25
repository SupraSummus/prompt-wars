from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from users.tests.factories import UserFactory

from ..models import Warrior
from ..tasks import do_moderation


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
    with patch('warriors.forms.async_task') as mocked_async_task:
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
    warrior_id = path.split('/')[-1]

    # right database state
    warrior = Warrior.objects.get(id=warrior_id)
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
    mocked_async_task.assert_called_once_with(do_moderation, warrior.id)

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
    warrior = Warrior.objects.get()
    assert warrior.arena == arena


@pytest.mark.django_db
def test_create_warrior_duplicate(client, warrior, mocked_recaptcha, default_arena):
    """It is not possible to create a warrior that has the same body as another."""
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': warrior.body,
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 200
    assert 'body' in response.context['form'].errors


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
    warrior = Warrior.objects.get()
    assert warrior.body == ' Test \nWarrior \n\n'


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
    warrior = Warrior.objects.get()
    assert warrior.created_by == user
    assert user in warrior.users.all()


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
def test_battle_details(client, battle):
    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200


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
