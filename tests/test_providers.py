import pytest
from openharness.providers import get_provider, OllamaProvider, OpenAICompatibleProvider


def test_provider_resolution():
    p1 = get_provider("ollama/llama3.1")
    assert isinstance(p1, OllamaProvider)
    assert p1.model == "llama3.1"

    p2 = get_provider("openai/gpt-4o")
    assert isinstance(p2, OpenAICompatibleProvider)
    assert p2.model == "gpt-4o"

    p3 = get_provider("vllm/qwen2.5-coder")
    assert isinstance(p3, OpenAICompatibleProvider)
    assert p3.base_url == "http://localhost:8000/v1"
