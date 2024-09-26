import datetime

import pytest

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
