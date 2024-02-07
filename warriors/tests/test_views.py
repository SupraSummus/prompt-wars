from unittest.mock import patch

import pytest
from django.urls import reverse
from django_recaptcha.client import RecaptchaResponse

from ..models import Warrior
from ..tasks import do_moderation


@pytest.fixture
def mocked_recaptcha(request):
    is_valid = getattr(request, 'param', True)
    with patch('django_recaptcha.fields.client.submit') as mocked_submit:
        mocked_submit.return_value = RecaptchaResponse(is_valid=is_valid)
        yield mocked_submit


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
    assert warrior.rating == 0.0
    assert warrior.games_played == 0
    assert warrior.next_battle_schedule is None
    assert warrior.moderation_date is None

    # moderation task scheduled
    mocked_async_task.assert_called_once_with(do_moderation, (warrior.id,))


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
