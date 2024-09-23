import logging

import anthropic
from django.conf import settings

from .exceptions import RateLimitError
from .models import MAX_WARRIOR_LENGTH


logger = logging.getLogger(__name__)

client = anthropic.Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
)


def resolve_battle(prompt_a, prompt_b, system_prompt=''):
    messages = [{
        'role': 'user',
        'content': prompt_a + prompt_b,
    }]
    extra_kwargs = {}
    if system_prompt:
        extra_kwargs['system_prompt'] = system_prompt
    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=MAX_WARRIOR_LENGTH,
            temperature=0,
            messages=messages,
            **extra_kwargs,
        )
    except anthropic.RateLimitError as e:
        raise RateLimitError() from e
    except anthropic.APIStatusError:
        logger.exception('Anthropic API call failed')
        return '', 'error', ''
    else:
        text = ''.join(block.text for block in response.content)
        return text, response.stop_reason, response.model
