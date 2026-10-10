import pytest
from django.urls import reverse

from llm_wars.home_view import example_battle
from warriors.tests.factories import (
    WarriorArenaFactory, WarriorUserPermissionFactory,
)


@pytest.mark.django_db
def test_home_without_an_arena(client):
    response = client.get(reverse('home'))
    assert response.status_code == 200
    assert response.context['top_warriors'] == []
    assert response.context['your_warriors'] == []


@pytest.mark.django_db
def test_home_shows_the_top_of_the_ladder(client, default_arena):
    low = WarriorArenaFactory(arena=default_arena, rating=10)
    high = WarriorArenaFactory(arena=default_arena, rating=500)
    WarriorArenaFactory(arena=default_arena, rating=900, warrior__moderation_passed=None)
    WarriorArenaFactory(rating=1000)  # another arena's
    response = client.get(reverse('home'))
    assert response.context['top_warriors'] == [high, low]


@pytest.mark.django_db
def test_home_lists_the_prompts_this_browser_made(client, default_arena):
    mine = WarriorArenaFactory(arena=default_arena)
    WarriorArenaFactory(arena=default_arena)
    session = client.session
    session['authorized_warriors'] = [str(mine.id), str(mine.warrior_id)]
    session.save()
    response = client.get(reverse('home'))
    assert response.context['your_warriors'] == [mine]
    # and the nudge to keep it
    assert 'Only this browser remembers this prompt' in response.content.decode()


@pytest.mark.django_db
def test_home_lists_an_accounts_prompts(user, user_client, default_arena):
    mine = WarriorArenaFactory(arena=default_arena)
    WarriorUserPermissionFactory(warrior=mine.warrior, user=user)
    WarriorArenaFactory(arena=default_arena)
    response = user_client.get(reverse('home'))
    assert response.context['your_warriors'] == [mine]


def test_example_marks_agree_with_its_percentages():
    """The card counts its marks as "kept of length repeated" and puts that beside each similarity."""
    for side in example_battle()['sides']:
        assert side['kept'] / side['length'] == side['similarity']
