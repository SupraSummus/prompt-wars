import pytest

from ..forms import clean_display_text


@pytest.mark.parametrize('typed, shown', [
    ('Evil\u202eredaeL', 'EvilredaeL'),
    ('\u2067Name\u2069 \u200f', 'Name'),
    ('tab\tand\nnewline', 'tabandnewline'),
    ('👨\u200d👩\u200d👧 family', '👨\u200d👩\u200d👧 family'),
])
def test_display_text_loses_controls_but_keeps_emoji_sequences(typed, shown):
    assert clean_display_text(typed) == shown
