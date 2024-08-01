import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse


@pytest.fixture
def room_change_permission(user):
    permission = Permission.objects.get(
        codename='change_room',
    )
    user.user_permissions.add(permission)


@pytest.mark.django_db
def test_root(user, user_client):
    response = user_client.get(reverse('labirynth:root', kwargs={
        'zoom_level': 0,
        'x': 0,
        'y': 0,
        'z': 0,
    }))
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('room', [{'prompt': 'old prompt'}], indirect=True)
def test_edit(user, user_client, room_change_permission, room):
    response = user_client.post(reverse('labirynth:edit', kwargs={
        'zoom_level': room.zoom_level,
        'x': room.x,
        'y': room.y,
        'z': room.z,
    }), data={
        'prompt': 'new prompt',
    })
    assert response.status_code == 200
    room.refresh_from_db()
    assert room.prompt == 'new prompt'
    version = room.versions.get()
    assert version.prompt == 'new prompt'
    assert version.user == user
