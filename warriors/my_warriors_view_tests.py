import pytest
from django.urls import reverse

from .rankings import Ranking


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'name': 'Warrior 1'}], indirect=True)
def test_index(
    user_client, warrior_user_permission,
    warrior, warrior_rating,
):
    response = user_client.get(reverse('my_warriors:index'))
    assert response.status_code == 200
    content = response.content.decode()
    assert warrior.name in content
    assert warrior_rating.get_absolute_url() in content
    for ranking in Ranking:
        assert str(ranking.label) in content


@pytest.mark.django_db
def test_logged_out_visitor_is_sent_to_log_in(client):
    response = client.get(reverse('my_warriors:index'))
    assert response.url.startswith(reverse('login') + '?next=')
