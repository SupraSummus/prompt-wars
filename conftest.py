from unittest.mock import patch

import pytest
from django_recaptcha.client import RecaptchaResponse


pytest_plugins = [
    'users.tests.fixtures',
    'warriors.tests.fixtures',
]


@pytest.fixture
def mocked_recaptcha(request):
    is_valid = getattr(request, 'param', True)
    with patch('django_recaptcha.fields.client.submit') as mocked_submit:
        mocked_submit.return_value = RecaptchaResponse(is_valid=is_valid)
        yield mocked_submit


@pytest.fixture
def user_client(client, user):
    client.force_login(user)
    return client
