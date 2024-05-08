import pytest
from django.urls import reverse

from .models import Player


@pytest.mark.django_db
def test_root_before_entering(user, user_client):
    print(reverse('labirynth:root'))
    response = user_client.get(reverse('labirynth:root'))
    assert response.status_code == 200
    assert not Player.objects.filter(user=user).exists()
