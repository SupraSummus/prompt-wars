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
def test_google_token_limit_reasoning():
    """This happens when the model never reaches end of reasoning."""
    responses.add(
        responses.POST,
        gemini_endpoint,
        json={
            'modelVersion': 'v1',
            'usageMetadata': {'promptTokenCount': 1, 'totalTokenCount': 1},
        },
    )
    text, finish_reason, llm_version = call_gemini('prompt')
    assert text == ''
    assert finish_reason == 'error'
    assert llm_version == 'v1'


@responses.activate
@pytest.mark.parametrize(
    ('generated_text_len', 'expected_finish_reason'),
    [
        (100, 'error'),
        (1000, 'MAX_TOKENS'),
        (10000, 'MAX_TOKENS'),
    ],
)
def test_google_token_limit_response(generated_text_len, expected_finish_reason):
    """This happens when the model starts generating response (after CoT) but reaches token limit."""
    responses.add(
        responses.POST,
        gemini_endpoint,
        json={
            'candidates': [{
                'content': {'parts': [
                    {'text': 'a' * generated_text_len},
                ], 'role': 'model'},
                'finishReason': 'MAX_TOKENS',
                'index': 0,
            }],
            'usageMetadata': {'promptTokenCount': 6, 'candidatesTokenCount': 45, 'totalTokenCount': 51},
            'modelVersion': 'gemini-2.0-flash-thinking-exp-01-21',
        },
    )
    text, finish_reason, llm_version = call_gemini('prompt')
    assert text == 'a' * generated_text_len
    assert finish_reason == expected_finish_reason
    assert llm_version == 'gemini-2.0-flash-thinking-exp-01-21'


@responses.activate
def test_google_no_finish_reason():
    """According to docs mising finish reason means the model "has not stopped generating the tokens".
    Lets treat that as transient error."""
    responses.add(
        responses.POST,
        gemini_endpoint,
        json={
            'candidates': [{
                'content': {'parts': [
                    {'text': 'a' * 100},
                ], 'role': 'model'},
                'index': 0,
            }],
            'usageMetadata': {'promptTokenCount': 6, 'candidatesTokenCount': 45, 'totalTokenCount': 51},
            'modelVersion': 'gemini-2.0-flash-thinking-exp-01-21',
        },
    )
    with pytest.raises(TransientLLMError):
        call_gemini('prompt')


@responses.activate
def test_google_no_text():
    responses.add(
        responses.POST,
        gemini_endpoint,
        json={
            'candidates': [{'finishReason': 'RECITATION', 'index': 0}],
            'modelVersion': 'gemini-2.0-flash-thinking-exp-01-21',
            'usageMetadata': {'promptTokenCount': 10, 'totalTokenCount': 10},
        },
    )
    text, finish_reason, llm_version = call_gemini('prompt')
    assert text == ''
    assert finish_reason == 'RECITATION'
    assert llm_version == 'gemini-2.0-flash-thinking-exp-01-21'
