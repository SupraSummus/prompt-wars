from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
from django.urls import reverse
from django.utils import timezone

from users.tests.factories import UserFactory

from ..models import Warrior
from ..tasks import do_moderation


@pytest.mark.django_db
def test_create_warrior_get(client):
    response = client.get(reverse('warrior_create'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_create_warrior(client, mocked_recaptcha):
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
    path, query = response.url.split('?')
    warrior_id = path.split('/')[-1]

    # right database state
    warrior = Warrior.objects.get(id=warrior_id)
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

    # user is redirected with secret key
    get_args = parse_qs(query)
    assert warrior.is_secret_valid(get_args['secret'][0])


@pytest.mark.django_db
def test_create_warrior_duplicate(client, warrior, mocked_recaptcha):
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
def test_create_no_strip(client, mocked_recaptcha):
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
def test_create_authenticated(user, user_client, mocked_recaptcha):
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
def test_battle_details(client, battle):
    response = client.get(
        reverse('battle_detail', args=(battle.id,))
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_leaderboard(client, warrior):
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
