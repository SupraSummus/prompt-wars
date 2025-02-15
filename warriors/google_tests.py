import pytest
import responses

from .exceptions import TransientLLMError
from .google import call_gemini


gemini_endpoint = 'https://generativelanguage.googleapis.com/v1alpha/models/gemini-2.0-flash-thinking-exp:generateContent'


@responses.activate
def test_google_503():
    responses.add(
        responses.POST,
        gemini_endpoint,
        status=503,
    )
    with pytest.raises(TransientLLMError):
        call_gemini('prompt')


@responses.activate
def test_google_token_limit():
    responses.add(
        responses.POST,
        gemini_endpoint,
        json={
            'candidates': [
                {},
            ],
            'modelVersion': 'v1',
        },
    )
    _, finish_reason, llm_version = call_gemini('prompt')
    assert finish_reason == 'error'
    assert llm_version == 'v1'
