from unittest.mock import patch

import pytest
from django_recaptcha.client import RecaptchaResponse


pytest_plugins = [
    'warriors.tests.fixtures',
]


@pytest.fixture
def mocked_recaptcha(request):
    is_valid = getattr(request, 'param', True)
    with patch('django_recaptcha.fields.client.submit') as mocked_submit:
        mocked_submit.return_value = RecaptchaResponse(is_valid=is_valid)
        yield mocked_submit
