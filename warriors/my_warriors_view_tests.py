import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'name': 'Warrior 1'}], indirect=True)
def test_index(user_client, warrior_user_permission, warrior):
    assert warrior.name
    assert warrior_user_permission.warrior is None
    warrior_user_permission.warrior = warrior
    warrior_user_permission.save()
    response = user_client.get(reverse('my_warriors:index'))
    assert response.status_code == 200
    assert warrior.name in response.content.decode()
