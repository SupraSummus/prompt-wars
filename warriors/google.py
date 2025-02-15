import requests
from django.conf import settings
from google import genai
from google.genai import types

from .exceptions import TransientLLMError


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
            config=types.GenerateContentConfig(
                temperature=0,
            ),
        )
        finish_reason = response.candidates[0].finish_reason.value
        return response.text, finish_reason, response.model_version
    except requests.HTTPError as e:
        if e.response.status_code >= 500:
            raise TransientLLMError() from e
        raise
    except requests.RequestException as e:
        raise TransientLLMError() from e
