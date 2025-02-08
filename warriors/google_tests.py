from .google import get_text_from_candidate


def test_get_text_from_candidate__no_content():
    assert get_text_from_candidate({}) == ''


def test_get_text_from_candidate__no_parts():
    assert get_text_from_candidate({'content': {}}) == ''


def test_get_text_from_candidate():
    assert get_text_from_candidate({
        'content': {
            'parts': [
                {'text': 'a'},
                {'text': 'b'},
            ],
        },
    }) == 'ab'
