import requests
from django.conf import settings


def get_voyage_embedding(text):
    """Get voyage-4-large binary embedding for a single text.

    Returns bit string of '0' and '1' characters (2048 bits),
    ready for pgvector BitField storage.
    """
    response = requests.post(
        'https://api.voyageai.com/v1/embeddings',
        headers={
            'Authorization': f'Bearer {settings.VOYAGE_API_KEY}',
            'Content-Type': 'application/json',
        },
        timeout=60,
        json={
            'input': [text],
            'model': 'voyage-4-large',
            'output_dimension': 2048,
            'output_dtype': 'ubinary',
        },
    )
    response.raise_for_status()

    data = response.json()['data']
    assert len(data) == 1
    packed = data[0]['embedding']
    return ''.join(format(b, '08b') for b in packed)
