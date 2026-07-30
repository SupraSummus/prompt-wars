import logging

import httpx
from django.conf import settings
from google import genai
from google.genai.errors import ClientError, ServerError
from google.genai.types import (
    FinishReason, GenerateContentConfig, ThinkingConfig,
)

from ..warriors import MAX_WARRIOR_LENGTH
from .exceptions import RateLimitError, TransientLLMError


logger = logging.getLogger(__name__)
client = genai.Client(
    api_key=settings.GOOGLE_AI_API_KEY,
)


def resolve_battle_google(prompt_a, prompt_b, system_prompt=''):
    assert not system_prompt
    return call_gemini(prompt_a + prompt_b)


def call_gemini(prompt):
    try:
        response = client.models.generate_content(
            model='gemini-flash-lite-latest',
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0,
                # arbitrary value to prevent looping in chain of thought
                # we allow for 1x thinking tokens and 1x output tokens, additional 1x for margin
                max_output_tokens=MAX_WARRIOR_LENGTH * 3,
                thinking_config=ThinkingConfig(
                    # a hint the model reasons past, not a cap - max_output_tokens is the cap
                    thinking_budget=MAX_WARRIOR_LENGTH * 1,
                ),
            ),
        )
    except ClientError as e:
        if e.code == 429:
            raise RateLimitError() from e
        raise
    except (ServerError, httpx.TransportError) as e:
        # the SDK's httpx transport never retries, so its resets and timeouts land here raw too
        raise TransientLLMError() from e

    # None whenever no candidate carries a text part - what reasoning eating the whole budget looks like
    text = response.text or ''
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None:
        finish_reason = 'error'
    elif candidate.finish_reason is None:
        raise TransientLLMError('Mode has not stoped generating tokens, whatever that means')
    else:
        finish_reason = candidate.finish_reason.value
        if (
            # battle is not valid if we exceed token limit and MAX_WARRIOR_LENGTH is not reached
            # model propably used all the tokens for reasoning
            finish_reason == FinishReason.MAX_TOKENS.value and
            len(text) < MAX_WARRIOR_LENGTH
        ):
            finish_reason = 'error'
    return text, finish_reason, response.model_version
