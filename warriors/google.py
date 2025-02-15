import logging

import requests
from django.conf import settings
from google import genai
from google.genai.errors import ServerError
from google.genai.types import FinishReason, GenerateContentConfig

from .exceptions import TransientLLMError
from .warriors import MAX_WARRIOR_LENGTH


logger = logging.getLogger(__name__)
client = genai.Client(
    api_key=settings.GOOGLE_AI_API_KEY,
    http_options={'api_version': 'v1alpha'},
)


def resolve_battle_google(prompt_a, prompt_b, system_prompt=''):
    assert not system_prompt
    return call_gemini(prompt_a + prompt_b)


def call_gemini(prompt):
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-thinking-exp',
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0,
                # arbitrary value to prevent looping in chain of thought
                max_output_tokens=MAX_WARRIOR_LENGTH * 20,
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
        if len(text) > MAX_WARRIOR_LENGTH * 10:
            logger.warning('Long battle result: %s chars', len(text))
        return text, finish_reason.value, response.model_version
    except ServerError as e:
        raise TransientLLMError() from e
    except requests.RequestException as e:
        raise TransientLLMError() from e
