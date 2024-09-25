import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_warrior_list(admin_client, warrior_arena):
    response = admin_client.get(reverse('admin:warriors_warriorarena_changelist'))
    assert response.status_code == 200
    assert str(warrior_arena.id) in response.content.decode('utf-8')
