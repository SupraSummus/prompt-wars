import logging

import openai
from django.conf import settings

from .exceptions import RateLimitError
from .models import MAX_WARRIOR_LENGTH


logger = logging.getLogger(__name__)

openai_client = openai.Client(
    api_key=settings.OPENAI_API_KEY,
)


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
            model='gpt-3.5-turbo',
            temperature=0,
            # Completion length limit is in tokens, so when measured in chars we will likely get more.
            # Other way arund is I think possible also - exotic unicode symbols
            # may be multiple LLM tokens, but a single char.
            # But this is a marginal case, so lets forget it for now.
            max_tokens=MAX_WARRIOR_LENGTH,
        )
    except openai.RateLimitError as e:
        raise RateLimitError() from e
    except openai.APIStatusError:
        logger.exception('OpenAI API call failed')
        return '', 'error', ''
    else:
        (resp_choice,) = response.choices
        result = resp_choice.message.content
        return (
            result,
            resp_choice.finish_reason,
            response.model + '/' + (response.system_fingerprint or '')
        )
