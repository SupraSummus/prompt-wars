import hashlib

import pytest
from django.urls import reverse

from embedding_explorer.models import (
    EMBEDDING_BITS, MAX_PHRASE_LENGTH, ExplorerQuery,
)
from users.tests.factories import UserFactory

from .models import Guess, GuessingTarget, _random_bits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_query(phrase, **kwargs):
    sha_256 = hashlib.sha256(phrase.encode('utf-8')).digest()
    return ExplorerQuery.objects.create(
        phrase=phrase,
        phrase_sha_256=sha_256,
        **kwargs,
    )


def _create_target(name, **kwargs):
    return GuessingTarget.objects.create(name=name, **kwargs)


def _create_guess(target, query, user):
    return Guess.objects.create(target=target, query=query, user=user)


# ---------------------------------------------------------------------------
# GuessingTarget model
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_target_gets_random_embedding_on_creation():
    target = _create_target('My Target')
    assert target.embedding is not None
    assert len(str(target.embedding)) == EMBEDDING_BITS


@pytest.mark.django_db
def test_two_targets_get_different_embeddings():
    t1 = _create_target('Target 1')
    t2 = _create_target('Target 2')
    assert str(t1.embedding) != str(t2.embedding)


@pytest.mark.django_db
def test_target_str():
    target = _create_target('My Target')
    assert str(target) == 'My Target'


def test_random_bits_length():
    assert len(_random_bits()) == EMBEDDING_BITS


def test_random_bits_charset():
    bits = _random_bits()
    assert set(bits) <= {'0', '1'}


# ---------------------------------------------------------------------------
# Guess model
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_guess_str(user):
    target = _create_target('Target')
    query = _create_query('my phrase')
    guess = _create_guess(target, query, user)
    assert 'my phrase' in str(guess)
    assert 'Target' in str(guess)


@pytest.mark.django_db
def test_guess_unique_per_target_query_user(user):
    from django.db import IntegrityError
    target = _create_target('Target')
    query = _create_query('same phrase')
    _create_guess(target, query, user)
    with pytest.raises(IntegrityError):
        _create_guess(target, query, user)


@pytest.mark.django_db
def test_guess_different_users_same_phrase_allowed(user):
    other_user = UserFactory()
    target = _create_target('Target')
    query = _create_query('same phrase')
    _create_guess(target, query, user)
    _create_guess(target, query, other_user)
    assert Guess.objects.count() == 2


# ---------------------------------------------------------------------------
# View tests — unauthenticated redirects
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list_requires_login(client):
    response = client.get(reverse('guessing:guessing_list'))
    assert response.status_code == 302
    assert '/login/' in response['Location']


@pytest.mark.django_db
def test_detail_requires_login(client):
    target = _create_target('Test Target')
    response = client.get(reverse('guessing:detail', kwargs={'target_id': target.id}))
    assert response.status_code == 302
    assert '/login/' in response['Location']


@pytest.mark.django_db
def test_guess_post_requires_login(client):
    target = _create_target('Test Target')
    response = client.post(
        reverse('guessing:guess_post', kwargs={'target_id': target.id}),
        data={'phrase': 'my guess'},
    )
    assert response.status_code == 302
    assert '/login/' in response['Location']


@pytest.mark.django_db
def test_guess_status_requires_login(client, user):
    target = _create_target('Target')
    query = _create_query('phrase')
    guess = _create_guess(target, query, user)
    response = client.get(reverse(
        'guessing:guess_status',
        kwargs={'guess_id': guess.id},
    ))
    assert response.status_code == 302
    assert '/login/' in response['Location']


# ---------------------------------------------------------------------------
# View tests — authenticated
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list(user_client):
    response = user_client.get(reverse('guessing:guessing_list'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_detail(user_client):
    target = _create_target('Test Target')
    response = user_client.get(reverse('guessing:detail', kwargs={'target_id': target.id}))
    assert response.status_code == 200
    assert 'Test Target' in response.content.decode()


@pytest.mark.django_db
def test_guess_post_creates_guess(user_client, user):
    target = _create_target('Test Target')
    response = user_client.post(
        reverse('guessing:guess_post', kwargs={'target_id': target.id}),
        data={'phrase': 'my guess phrase'},
    )
    assert response.status_code == 302
    guess = Guess.objects.get()
    assert guess.query.phrase == 'my guess phrase'
    assert guess.target == target
    assert guess.user == user


@pytest.mark.django_db
def test_guess_post_duplicate_phrase_reuses_guess(user_client):
    target = _create_target('Test Target')
    url = reverse('guessing:guess_post', kwargs={'target_id': target.id})
    user_client.post(url, data={'phrase': 'repeated guess'})
    user_client.post(url, data={'phrase': 'repeated guess'})
    assert Guess.objects.count() == 1


@pytest.mark.django_db
def test_guess_post_phrase_too_long(user_client):
    target = _create_target('Test Target')
    response = user_client.post(
        reverse('guessing:guess_post', kwargs={'target_id': target.id}),
        data={'phrase': 'x' * (MAX_PHRASE_LENGTH + 1)},
    )
    assert response.status_code == 200
    assert Guess.objects.count() == 0


@pytest.mark.django_db
def test_detail_shows_distance_when_embedding_ready(user_client, user):
    bits_target = '0' * EMBEDDING_BITS
    bits_guess = '1' * 10 + '0' * (EMBEDDING_BITS - 10)
    target = _create_target('Target', embedding=bits_target)
    query = _create_query('close guess', embedding=bits_guess)
    _create_guess(target, query, user)

    content = user_client.get(
        reverse('guessing:detail', kwargs={'target_id': target.id})
    ).content.decode()
    assert 'close guess' in content
    assert 'Distance: 10' in content


@pytest.mark.django_db
def test_detail_shows_pending_when_embedding_missing(user_client, user):
    target = _create_target('Target')
    query = _create_query('pending guess')  # no embedding
    _create_guess(target, query, user)

    content = user_client.get(
        reverse('guessing:detail', kwargs={'target_id': target.id})
    ).content.decode()
    assert 'pending guess' in content
    assert 'computing' in content.lower()


@pytest.mark.django_db
def test_detail_only_shows_own_guesses(user_client, user):
    other_user = UserFactory()
    target = _create_target('Target', embedding='0' * EMBEDDING_BITS)
    my_query = _create_query('my phrase', embedding='0' * EMBEDDING_BITS)
    other_query = _create_query('other phrase', embedding='0' * EMBEDDING_BITS)
    _create_guess(target, my_query, user)
    _create_guess(target, other_query, other_user)

    content = user_client.get(
        reverse('guessing:detail', kwargs={'target_id': target.id})
    ).content.decode()
    assert 'my phrase' in content
    assert 'other phrase' not in content


@pytest.mark.django_db
def test_guess_status_computed(user_client, user):
    bits_target = '0' * EMBEDDING_BITS
    bits_guess = '1' * 20 + '0' * (EMBEDDING_BITS - 20)
    target = _create_target('Target', embedding=bits_target)
    query = _create_query('test phrase', embedding=bits_guess)
    guess = _create_guess(target, query, user)

    response = user_client.get(reverse(
        'guessing:guess_status',
        kwargs={'guess_id': guess.id},
    ))
    content = response.content.decode()
    assert 'Distance: 20' in content
    assert 'hx-get' not in content


@pytest.mark.django_db
def test_guess_status_pending(user_client, user):
    target = _create_target('Target')
    query = _create_query('pending phrase')
    guess = _create_guess(target, query, user)

    response = user_client.get(reverse(
        'guessing:guess_status',
        kwargs={'guess_id': guess.id},
    ))
    content = response.content.decode()
    assert 'hx-get' in content
    assert 'computing' in content.lower()
