import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_root(user, user_client):
    response = user_client.get(reverse('labirynth:root', kwargs={
        'zoom_level': 0,
        'x': 0,
        'y': 0,
        'z': 0,
    }))
    assert response.status_code == 200
