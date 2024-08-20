from unittest.mock import patch

import factory
import pytest
from django.contrib.sites.models import Site
from django_recaptcha.client import RecaptchaResponse


pytest_plugins = [
    'users.tests.fixtures',
    'warriors.tests.fixtures',
    'labirynth.fixtures',
    'stories.fixtures',
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


class SiteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Site

    domain = factory.Sequence(lambda n: f'n{n}.example.com')


@pytest.fixture
def site():
    return SiteFactory()
