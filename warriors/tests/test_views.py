from unittest.mock import patch

import pytest
from django.urls import reverse

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
                'author': 'Test Author',
                'body': 'Test Body',
                'g-recaptcha-response': 'PASSED',
            },
        )
    assert response.status_code == 302, response.context['form'].errors
    warrior_id = response.url.split('/')[-1]

    # right database state
    warrior = Warrior.objects.get(id=warrior_id)
    assert warrior.name == 'Test Warrior'
    assert warrior.author == 'Test Author'
    assert warrior.body == 'Test Body'
    assert len(warrior.body_sha_256) == 32
    assert warrior.rating == 0.0
    assert warrior.games_played == 0
    assert warrior.next_battle_schedule is None
    assert warrior.moderation_date is None

    # moderation task scheduled
    mocked_async_task.assert_called_once_with(do_moderation, warrior.id)


@pytest.mark.django_db
def test_create_warrior_duplicate(client, warrior, mocked_recaptcha):
    response = client.post(
        reverse('warrior_create'),
        data={
            'name': warrior.name,
            'author': warrior.author,
            'body': warrior.body,
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 200
    assert 'body' in response.context['form'].errors


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [
    {'moderation_passed': False},
    {'moderation_passed': True},
    {'moderation_passed': None},
], indirect=True)
def test_warrior_details(client, warrior):
    response = client.get(
        reverse('warrior_detail', args=(warrior.id,))
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_leaderboard(client, warrior):
    response = client.get(reverse('warrior_leaderboard'))
    assert response.status_code == 200
    assert warrior in response.context['warriors']
