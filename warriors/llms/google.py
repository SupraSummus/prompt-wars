import logging

import requests
from django.conf import settings
from google import genai
from google.genai.errors import ServerError
from google.genai.types import (
    FinishReason, GenerateContentConfig, ThinkingConfig,
)

from ..warriors import MAX_WARRIOR_LENGTH
from .exceptions import TransientLLMError


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
            model='gemini-2.5-flash-preview-04-17',
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0,
                # arbitrary value to prevent looping in chain of thought
                # we allow for 4x thinking tokens and 1x output tokens, additional 1x for margin
                max_output_tokens=MAX_WARRIOR_LENGTH * 6,
                thinking_config=ThinkingConfig(
                    thinking_budget=MAX_WARRIOR_LENGTH * 4,
                ),
            ),
        )
        candidates = response.candidates
        if not candidates:
            return '', 'error', response.model_version
        finish_reason = candidates[0].finish_reason
        if finish_reason is None:
            raise TransientLLMError('Mode has not stoped generating tokens, whatever that means')
        text = response.text or ''
        if (
            # battle is not valid if we exceed token limit and MAX_WARRIOR_LENGTH is not reached
            # model propably used all the tokens for reasoning
            finish_reason == FinishReason.MAX_TOKENS and
            len(text) < MAX_WARRIOR_LENGTH
        ):
            return response.text, 'error', response.model_version
        return text, finish_reason.value, response.model_version
    except ServerError as e:
        raise TransientLLMError() from e
    except requests.RequestException as e:
        raise TransientLLMError() from e
