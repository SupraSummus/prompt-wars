import json

import requests
from django.conf import settings

from .warriors import MAX_WARRIOR_LENGTH


def resolve_battle_google(prompt_a, prompt_b, system_prompt=''):
    assert not system_prompt
    return call_gemini(prompt_a + prompt_b)


def call_gemini(prompt, break_at_length=MAX_WARRIOR_LENGTH):
    model = "gemini-2.0-flash-thinking-exp"
    chunks = []
    total_length = 0
    finish_reason = None
    reported_model = None
    with requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent',
        headers={
            'Content-Type': 'application/json',
        },
        params={
            'alt': 'sse',
            'key': settings.GOOGLE_AI_API_KEY,
        },
        json={
            'contents': [{
                'parts': [{
                    'text': prompt,
                }],
            }],
            'generationConfig': {
                'temperature': 0,
                'maxOutputTokens': break_at_length * 10,  # prevent looping inside internal monologue
            },
        },
        stream=True,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            line = line.decode('utf-8')
            if not line.startswith('data:'):
                continue
            data = json.loads(line[len(b'data:'):])
            candidate = data['candidates'][0]

            for chunk in candidate['content']['parts']:
                chunks.append(chunk)
                total_length += len(chunk['text'])

            finish_reason = candidate.get('stopReason') or finish_reason
            reported_model = data.get('modelVersion') or reported_model

            if total_length > break_at_length:
                break

    total_text = ''.join(chunk['text'] for chunk in chunks)
    return total_text, finish_reason, reported_model
