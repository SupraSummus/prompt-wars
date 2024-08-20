import factory
import pytest

from .models import Chunk


@pytest.fixture
def chunk(request):
    return ChunkFactory(
        **getattr(request, 'param', {}),
    )


class ChunkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Chunk
