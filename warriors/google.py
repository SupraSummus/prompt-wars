import requests
from django.conf import settings
from google import genai
from google.genai.errors import ServerError
from google.genai.types import GenerateContentConfig

from .exceptions import TransientLLMError
from .warriors import MAX_WARRIOR_LENGTH


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
                max_output_tokens=MAX_WARRIOR_LENGTH * 100,
            ),
        )
        finish_reason = response.candidates[0].finish_reason
        if finish_reason is None:  # exceeded token limit we treat as battle-not-valid
            return response.text, 'error', response.model_version
        return response.text, finish_reason.value, response.model_version
    except ServerError as e:
        raise TransientLLMError() from e
    except requests.RequestException as e:
        raise TransientLLMError() from e
