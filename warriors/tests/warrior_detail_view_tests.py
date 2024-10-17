import pytest
from django.urls import reverse
from warriors.models import WarriorArena

@pytest.mark.django_db
def test_warrior_detail_view_200(client):
    warrior = WarriorArena.objects.create(name="Test Warrior")
    url = reverse('global_warrior_detail', kwargs={'warrior_id': warrior.id})
    response = client.get(url)
    assert response.status_code == 200
