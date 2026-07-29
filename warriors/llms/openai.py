import logging

import openai
from django.conf import settings

from ..warriors import MAX_WARRIOR_LENGTH
from .exceptions import RateLimitError, TransientLLMError


logger = logging.getLogger(__name__)

openai_client = openai.Client(
    api_key=settings.OPENAI_API_KEY,
)


def _llm_version(response):
    """Which model actually answered.

    Unlike the other providers, openai splits this across two fields -
    the resolved model name and a fingerprint of the backend behind it.
    """
    return response.model + '/' + (response.system_fingerprint or '')


def resolve_battle_openai(prompt_a, prompt_b, system_prompt=''):
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({
        'role': 'user',
        'content': prompt_a + prompt_b,
    })
    try:
        response = openai_client.chat.completions.create(
            messages=messages,
            model='gpt-5-mini',
            reasoning_effort='low',
            # Completion length limit is in tokens, so when measured in chars we will likely get more.
            # Other way arund is I think possible also - exotic unicode symbols
            # may be multiple LLM tokens, but a single char.
            # But this is a marginal case, so lets forget it for now.
            # 1x reasoning tokens, 1x output tokens, additional 1x for margin
            max_completion_tokens=MAX_WARRIOR_LENGTH * 3,
        )
    except openai.RateLimitError as e:
        raise RateLimitError() from e
    except openai.APIStatusError as e:
        if e.response.status_code >= 500:
            raise TransientLLMError() from e
        raise
    else:
        (resp_choice,) = response.choices
        finish_reason = resp_choice.finish_reason
        # content is Optional in the response schema, hence the fallback
        result = resp_choice.message.content or ''
        if (
            # battle is not valid if we exceed token limit and MAX_WARRIOR_LENGTH is not reached
            # model propably used all the tokens for reasoning
            finish_reason == 'length' and
            len(result) < MAX_WARRIOR_LENGTH
        ):
            finish_reason = 'error'
        return result, finish_reason, _llm_version(response)


def call_llm(examples, prompt, system_prompt=None, max_completion_tokens=None):
    messages = []
    if system_prompt is not None:
        messages.append({'role': 'system', 'content': system_prompt})
    for user_text, ai_text in examples:
        messages.append({
            'role': 'user',
            'content': user_text,
        })
        messages.append({
            'role': 'assistant',
            'content': ai_text,
        })
    messages.append({
        'role': 'user',
        'content': prompt,
    })
    kwargs = {}
    if max_completion_tokens is not None:
        kwargs['max_completion_tokens'] = max_completion_tokens
    response = openai_client.chat.completions.create(
        messages=messages,
        model='gpt-5',
        **kwargs,
    )
    (resp_choice,) = response.choices
    return resp_choice.message.content, _llm_version(response)
