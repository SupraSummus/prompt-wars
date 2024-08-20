import pytest
from django.urls import reverse

from .fixtures import ChunkFactory


@pytest.mark.django_db
@pytest.mark.parametrize('chunk', [{'text': 'Hello, world!'}], indirect=True)
def test_index(chunk, client):
    next_chunk = ChunkFactory(previous_chunk=chunk, text='Goodbye, world!')
    next_next_chunk = ChunkFactory(previous_chunk=next_chunk, text='Hello again!')
    for c in [chunk, next_chunk, next_next_chunk]:
        assert c.text
    response = client.get(reverse('stories:index', args=[next_chunk.id]))
    assert response.status_code == 200
    content = response.content.decode()
    for c in [next_chunk, next_next_chunk]:
        assert c.text in content
