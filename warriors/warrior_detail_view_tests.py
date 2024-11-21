import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_warrior_detail_view(client, warrior):
    url = reverse('warrior_detail:root', kwargs={'warrior_id': warrior.id})
    response = client.get(url)
    assert response.status_code == 200
