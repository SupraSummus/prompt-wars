import pytest
from django.urls import reverse

from .factories import HillAttemptFactory


@pytest.mark.django_db
@pytest.mark.parametrize('model', ['hill', 'round', 'hillattempt'])
def test_lists(admin_client, open_round, model):
    HillAttemptFactory(hill_round=open_round)
    response = admin_client.get(reverse(f'admin:hill_{model}_changelist'))
    assert response.status_code == 200
