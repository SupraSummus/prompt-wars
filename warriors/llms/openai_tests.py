import pytest

from .openai import resolve_battle_openai


@pytest.mark.real_world
def test_resolve_battle_openai_real_endpoint():
    text, finish_reason, llm_version = resolve_battle_openai(
        'Test text',
        'Another test text',
    )
    assert isinstance(text, str)
    assert isinstance(finish_reason, str)
    assert isinstance(llm_version, str)
