import datetime
from unittest import mock

import pytest
from django.utils import timezone
from django_goals.busy_worker import worker_turn

from .text_unit import TextUnit


@pytest.mark.django_db
def test_text_unit_get_or_create_updates_created_at():
    now = datetime.datetime(2021, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    text_unit = TextUnit.get_or_create_by_content('content', now=now)
    assert text_unit.created_at == now

    then = now - datetime.timedelta(days=1)
    TextUnit.get_or_create_by_content('content', now=then)
    text_unit.refresh_from_db()
    assert text_unit.created_at == then


@pytest.mark.django_db
def test_embedding():
    text_unit = TextUnit.get_or_create_by_content('content')
    assert text_unit.voyage_3_embedding_goal is not None
    assert not text_unit.voyage_3_embedding

    with mock.patch('warriors.embeddings.get_embedding') as get_embedding:
        get_embedding.return_value = [0.0] * 1024
        worker_turn(timezone.now())

    assert get_embedding.call_count == 1
    assert get_embedding.call_args[0][0] == 'content'

    text_unit.refresh_from_db()
    assert text_unit.voyage_3_embedding is not None
    assert len(text_unit.voyage_3_embedding) == 1024
