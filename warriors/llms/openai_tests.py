import pytest

from ..warriors import MAX_WARRIOR_LENGTH
from .exceptions import RateLimitError, TransientLLMError
from .openai import resolve_battle_openai


openai_endpoint = 'https://api.openai.com/v1/chat/completions'


def chat_completion(finish_reason, content, system_fingerprint=None):
    return {
        'id': 'chatcmpl-1',
        'object': 'chat.completion',
        'created': 1785345620,
        'model': 'gpt-5-mini-2025-08-07',
        'system_fingerprint': system_fingerprint,
        'choices': [{
            'index': 0,
            'finish_reason': finish_reason,
            'message': {'role': 'assistant', 'content': content},
        }],
    }


def test_openai_429(httpx2_mock):
    httpx2_mock.post(openai_endpoint).respond(429)
    with pytest.raises(RateLimitError):
        resolve_battle_openai('prompt a', 'prompt b')


def test_openai_503(httpx2_mock):
    httpx2_mock.post(openai_endpoint).respond(503)
    with pytest.raises(TransientLLMError):
        resolve_battle_openai('prompt a', 'prompt b')


@pytest.mark.parametrize('content', ['', None])
def test_openai_token_limit_reasoning(content, httpx2_mock):
    """This happens when the model never reaches end of reasoning.

    The live endpoint sends an empty string, the schema permits null.
    """
    httpx2_mock.post(openai_endpoint).respond(200, json=chat_completion('length', content))
    text, finish_reason, llm_version = resolve_battle_openai('prompt a', 'prompt b')
    assert text == ''
    assert finish_reason == 'error'
    assert llm_version == 'gpt-5-mini-2025-08-07/'


@pytest.mark.parametrize(
    ('generated_text_len', 'expected_finish_reason'),
    [
        (MAX_WARRIOR_LENGTH - 1, 'error'),
        (MAX_WARRIOR_LENGTH, 'length'),
    ],
)
def test_openai_token_limit_response(generated_text_len, expected_finish_reason, httpx2_mock):
    """This happens when the model starts generating response (after CoT) but reaches token limit.

    A response that made it to full length counts, a shorter one doesn't.
    """
    httpx2_mock.post(openai_endpoint).respond(
        200,
        json=chat_completion('length', 'a' * generated_text_len),
    )
    text, finish_reason, llm_version = resolve_battle_openai('prompt a', 'prompt b')
    assert text == 'a' * generated_text_len
    assert finish_reason == expected_finish_reason
    assert llm_version == 'gpt-5-mini-2025-08-07/'


def test_openai_stop(httpx2_mock):
    """A short answer is fine as long as the model chose to stop."""
    httpx2_mock.post(openai_endpoint).respond(200, json=chat_completion(
        'stop', 'a' * 100, system_fingerprint='fp_deadbeef',
    ))
    text, finish_reason, llm_version = resolve_battle_openai('prompt a', 'prompt b')
    assert text == 'a' * 100
    assert finish_reason == 'stop'
    assert llm_version == 'gpt-5-mini-2025-08-07/fp_deadbeef'


@pytest.mark.real_world
def test_resolve_battle_openai_real_endpoint():
    text, finish_reason, llm_version = resolve_battle_openai(
        'Test text',
        'Another test text',
    )
    assert isinstance(text, str)
    assert isinstance(finish_reason, str)
    assert isinstance(llm_version, str)
