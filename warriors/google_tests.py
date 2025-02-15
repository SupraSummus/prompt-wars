import pytest
import responses

from .exceptions import TransientLLMError
from .google import call_gemini


@responses.activate
def test_google_503():
    responses.add(
        responses.POST,
        'https://generativelanguage.googleapis.com/v1alpha/models/gemini-2.0-flash-thinking-exp:streamGenerateContent',
        status=503,
    )
    with pytest.raises(TransientLLMError):
        call_gemini('prompt')
