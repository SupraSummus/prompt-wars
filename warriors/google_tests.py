import pytest
import responses

from .exceptions import TransientLLMError
from .google import call_gemini, get_text_from_candidate


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


@responses.activate
def test_google_503():
    responses.add(
        responses.POST,
        'https://generativelanguage.googleapis.com/v1alpha/models/gemini-2.0-flash-thinking-exp:streamGenerateContent',
        status=503,
    )
    with pytest.raises(TransientLLMError):
        call_gemini('prompt')
