import pytest
from django.urls import reverse

from .models import Player, Room, EMBEDDING_DIM


@pytest.mark.django_db
def test_root_before_entering(user, user_client):
    print(reverse('labirynth:root'))
    response = user_client.get(reverse('labirynth:root'))
    assert response.status_code == 200
    assert not Player.objects.filter(user=user).exists()
@pytest.mark.django_db
def test_user_in_room(user, user_client):
    # Create a room and assign it to a player
    room = Room.objects.create(
        x=0,
        y=0,
        z=0,
        prompt="Room 1",
        som_neurons=[[0.0] * EMBEDDING_DIM for _ in range(6)]
    )
    player = Player.objects.create(user=user, current_room=room)
    
    # Make a GET request to the root view
    response = user_client.get(reverse('labirynth:root'))
    
    # Verify the response status code
    assert response.status_code == 200
    
    # Verify the room's prompt is presented in the response
    assert "Room 1" in response.content.decode()
