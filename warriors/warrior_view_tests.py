import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{'body': 'asdf1234'}], indirect=True)
def test_warrior_detail_basic(client, warrior, arena):
    """Test that warrior detail page loads correctly with basic information"""
    response = client.get(
        reverse('warrior:get', args=(warrior.id,))
    )
    assert response.status_code == 200
    assert response.context['warrior'] == warrior
    assert response.context['show_secrets'] is False
    assert warrior.body not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [
    {'name': 'asdf1234', 'author_name': 'qwerty', 'moderation_passed': True},
    {'name': 'asdf1234', 'author_name': 'qwerty', 'moderation_passed': False},
    {'name': 'asdf1234', 'author_name': 'qwerty', 'moderation_passed': None},
], indirect=True)
def test_warrior_detail_moderation_states(client, warrior):
    """Test that warrior detail page shows correct moderation state"""
    response = client.get(
        reverse('warrior:get', args=(warrior.id,))
    )
    assert response.status_code == 200
    content = response.content.decode()

    if warrior.moderation_passed is None:
        show_content = False
        assert 'moderation pending' in content

    elif not warrior.moderation_passed:
        show_content = False
        assert 'moderation failed' in content

    else:
        show_content = True

    assert (warrior.name in content) == show_content
    assert (warrior.author_name in content) == show_content


@pytest.mark.django_db
def test_link_to_warrior_arena(client, warrior, warrior_arena):
    """Warrior detail page shows link to warrior-arena"""
    response = client.get(
        reverse('warrior:get', args=(warrior.id,))
    )
    assert response.status_code == 200
    assert warrior_arena in response.context['warrior_arenas']
