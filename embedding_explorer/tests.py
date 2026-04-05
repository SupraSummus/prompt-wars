import hashlib
from unittest.mock import Mock, patch

import pytest
import requests
from django.urls import reverse
from django_goals.models import AllDone, RetryMeLater

from .models import (
    EMBEDDING_BITS, MAX_PHRASE_LENGTH, ExplorerQuery, _ensure_embedding,
)


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).digest()


def _create_query(phrase, **kwargs):
    return ExplorerQuery.objects.create(
        phrase=phrase,
        phrase_sha_256=_sha256(phrase),
        **kwargs,
    )


@pytest.mark.django_db
def test_index_get(client):
    response = client.get(reverse('embedding_explorer:index_get'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_index_get_csrf_token_rendered(client):
    """CSRF token must be rendered as a hidden input, not as a raw template tag."""
    response = client.get(reverse('embedding_explorer:index_get'))
    content = response.content.decode()
    assert '{% csrf_token %}' not in content
    assert 'csrfmiddlewaretoken' in content


@pytest.mark.django_db
def test_create_query(client):
    response = client.post(
        reverse('embedding_explorer:index_post'),
        data={'phrase': 'hello world'},
    )
    assert response.status_code == 302

    query = ExplorerQuery.objects.get()
    assert query.phrase == 'hello world'
    assert query.phrase_sha_256 == _sha256('hello world')
    assert query.embedding is None
    assert query.embedding_goal is not None


@pytest.mark.django_db
def test_create_query_too_long(client):
    response = client.post(
        reverse('embedding_explorer:index_post'),
        data={'phrase': 'a' * (MAX_PHRASE_LENGTH + 1)},
    )
    assert response.status_code == 200
    assert not ExplorerQuery.objects.exists()


@pytest.mark.django_db
def test_create_query_duplicate(client):
    """Submitting the same phrase twice returns the existing query."""
    response = client.post(
        reverse('embedding_explorer:index_post'),
        data={'phrase': 'duplicate phrase'},
    )
    assert response.status_code == 302
    first_id = response.url.split('/')[-2]

    response = client.post(
        reverse('embedding_explorer:index_post'),
        data={'phrase': 'duplicate phrase'},
    )
    assert response.status_code == 302
    second_id = response.url.split('/')[-2]

    assert first_id == second_id
    assert ExplorerQuery.objects.count() == 1


@pytest.mark.django_db
def test_detail_view(client):
    query = _create_query('test phrase')
    response = client.get(reverse('embedding_explorer:detail', kwargs={'query_id': query.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_detail_view_with_embedding(client):
    bits = '0' * EMBEDDING_BITS
    query = _create_query('test phrase', embedding=bits)
    response = client.get(reverse('embedding_explorer:detail', kwargs={'query_id': query.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_ensure_embedding_retry_on_http_failure(settings):
    settings.VOYAGE_API_KEY = 'test-key'
    query = _create_query('test phrase')
    query.schedule_embedding()

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.RequestException('API error')

    with patch('requests.post', return_value=mock_response):
        result = _ensure_embedding(query.embedding_goal)
        assert isinstance(result, RetryMeLater)

    query.refresh_from_db()
    assert query.embedding is None


@pytest.mark.django_db
def test_embedding_end_to_end(settings):
    """Test full chain: _ensure_embedding -> voyage HTTP API -> pgvector storage."""
    settings.VOYAGE_API_KEY = 'test-key'

    fake_packed = list(range(256))
    expected_bits = ''.join(format(b, '08b') for b in fake_packed)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {
        'data': [{'embedding': fake_packed, 'index': 0}],
        'model': 'voyage-4-large',
        'usage': {'total_tokens': 5},
    }

    query = _create_query('hello world')
    query.schedule_embedding()

    with patch('requests.post', return_value=mock_response) as mock_post:
        result = _ensure_embedding(query.embedding_goal)

    assert isinstance(result, AllDone)

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs['json']['model'] == 'voyage-4-large'
    assert call_kwargs.kwargs['json']['output_dtype'] == 'ubinary'
    assert call_kwargs.kwargs['json']['output_dimension'] == 2048
    assert call_kwargs.kwargs['json']['input'] == ['hello world']
    assert 'Bearer test-key' in call_kwargs.kwargs['headers']['Authorization']

    query.refresh_from_db()
    assert query.embedding is not None
    assert str(query.embedding) == expected_bits


@pytest.mark.django_db
def test_detail_view_nearest_entries(client):
    """Nearest entries are shown on the detail page with links and distances."""
    # Create a query with all-zero embedding
    bits_a = '0' * EMBEDDING_BITS
    query_a = _create_query('phrase a', embedding=bits_a)

    # Create a near neighbor (distance = 10)
    bits_b = '1' * 10 + '0' * (EMBEDDING_BITS - 10)
    query_b = _create_query('phrase b', embedding=bits_b)

    # Create a far neighbor (distance > 400, should be excluded)
    bits_c = '1' * 500 + '0' * (EMBEDDING_BITS - 500)
    _create_query('phrase c', embedding=bits_c)

    response = client.get(reverse(
        'embedding_explorer:detail', kwargs={'query_id': query_a.id},
    ))
    content = response.content.decode()

    # Near neighbor should appear with link and distance
    assert 'phrase b' in content
    assert str(query_b.id) in content
    assert '10' in content

    # Far neighbor should not appear
    assert 'phrase c' not in content


@pytest.mark.django_db
def test_detail_view_nearest_entries_no_embedding(client):
    """When embedding is not computed, show appropriate message."""
    query = _create_query('no embedding')
    response = client.get(reverse(
        'embedding_explorer:detail', kwargs={'query_id': query.id},
    ))
    content = response.content.decode()
    assert 'not yet computed' in content


@pytest.mark.django_db
def test_status_pending(client):
    query = _create_query('test phrase')
    response = client.get(reverse('embedding_explorer:status', kwargs={'query_id': query.id}))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'hx-get' in content
    assert 'Pending' in content


@pytest.mark.django_db
def test_status_computed(client):
    bits = '0' * EMBEDDING_BITS
    query = _create_query('test phrase', embedding=bits)
    response = client.get(reverse('embedding_explorer:status', kwargs={'query_id': query.id}))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'hx-get' not in content
    assert 'Computed' in content


@pytest.mark.django_db
def test_status_computed_includes_nearest_entries(client):
    """When embedding is computed, status response includes nearest entries."""
    bits_a = '0' * EMBEDDING_BITS
    query_a = _create_query('phrase a', embedding=bits_a)

    bits_b = '1' * 10 + '0' * (EMBEDDING_BITS - 10)
    _create_query('phrase b', embedding=bits_b)

    response = client.get(reverse('embedding_explorer:status', kwargs={'query_id': query_a.id}))
    content = response.content.decode()
    assert 'Nearest entries' in content
    assert 'phrase b' in content


@pytest.mark.django_db
def test_status_pending_includes_nearest_entries_placeholder(client):
    """When embedding is pending, status response includes nearest entries placeholder."""
    query = _create_query('test phrase')
    response = client.get(reverse('embedding_explorer:status', kwargs={'query_id': query.id}))
    content = response.content.decode()
    assert 'not yet computed' in content
