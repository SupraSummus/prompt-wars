import pytest
from django.urls import reverse

from .models import Player


@pytest.mark.django_db
def test_root_before_entering(user, user_client):
    response = user_client.get(reverse('labirynth:root'))
    assert response.status_code == 200
    assert not Player.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_start(user, user_client):
    response = user_client.post(reverse('labirynth:start'))
    assert response.status_code == 200
    player = Player.objects.get(user=user)
    assert player.current_room is not None


@pytest.mark.django_db
def test_user_in_room(user_client, player, room):
    response = user_client.get(reverse('labirynth:root'))
    assert response.status_code == 200
    assert response.context['current_room'] == room
