import pytest
import respx

from .exceptions import TransientLLMError
from .google import call_gemini


gemini_endpoint = 'https://generativelanguage.googleapis.com/v1alpha/models/gemini-2.0-flash-thinking-exp:generateContent'


@respx.mock
def test_google_503():
    respx.post(gemini_endpoint).respond(503)
    with pytest.raises(TransientLLMError):
        call_gemini('prompt')


@respx.mock
def test_google_token_limit_reasoning():
    """This happens when the model never reaches end of reasoning."""
    respx.post(gemini_endpoint).respond(
        200,
        json={
            'modelVersion': 'v1',
            'usageMetadata': {'promptTokenCount': 1, 'totalTokenCount': 1},
        }
    )
    text, finish_reason, llm_version = call_gemini('prompt')
    assert text == ''
    assert finish_reason == 'error'
    assert llm_version == 'v1'


@respx.mock
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
    respx.post(gemini_endpoint).respond(
        200,
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
        }
    )
    text, finish_reason, llm_version = call_gemini('prompt')
    assert text == 'a' * generated_text_len
    assert finish_reason == expected_finish_reason
    assert llm_version == 'gemini-2.0-flash-thinking-exp-01-21'


@respx.mock
def test_google_no_finish_reason():
    """According to docs mising finish reason means the model "has not stopped generating the tokens".
    Lets treat that as transient error."""
    respx.post(gemini_endpoint).respond(
        200,
        json={
            'candidates': [{
                'content': {'parts': [
                    {'text': 'a' * 100},
                ], 'role': 'model'},
                'index': 0,
            }],
            'usageMetadata': {'promptTokenCount': 6, 'candidatesTokenCount': 45, 'totalTokenCount': 51},
            'modelVersion': 'gemini-2.0-flash-thinking-exp-01-21',
        }
    )
    with pytest.raises(TransientLLMError):
        call_gemini('prompt')


@respx.mock
def test_google_no_text():
    respx.post(gemini_endpoint).respond(
        200,
        json={
            'candidates': [{'finishReason': 'RECITATION', 'index': 0}],
            'modelVersion': 'gemini-2.0-flash-thinking-exp-01-21',
            'usageMetadata': {'promptTokenCount': 10, 'totalTokenCount': 10},
        }
    )
    text, finish_reason, llm_version = call_gemini('prompt')
    assert text == ''
    assert finish_reason == 'RECITATION'
    assert llm_version == 'gemini-2.0-flash-thinking-exp-01-21'
