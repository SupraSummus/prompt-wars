import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_no_smoke(client):
    response = client.get(reverse('data_policy:root'))
    assert response.status_code == 200
