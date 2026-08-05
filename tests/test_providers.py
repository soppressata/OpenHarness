import pytest
from openharness.providers import get_provider, check_provider_health
from openharness.providers.base import BaseProvider, ProviderResponse
from openharness.providers.local_ollama import OllamaProvider
from openharness.providers.openai_compatible import OpenAICompatibleProvider


class MockCustomProvider(BaseProvider):
    def generate(self, prompt, **kwargs):
        return ProviderResponse(content="Custom mock response", model="mock-model")

    async def agenerate(self, prompt, **kwargs):
        return ProviderResponse(content="Custom mock response", model="mock-model")

    def check_connection(self) -> bool:
        return True


def test_provider_factory():
    p1 = get_provider("ollama/llama3.1")
    assert isinstance(p1, OllamaProvider)
    assert p1.model == "llama3.1"

    p2 = get_provider("vllm/qwen2.5")
    assert isinstance(p2, OpenAICompatibleProvider)
    assert p2.model == "qwen2.5"

    p3 = get_provider("openai/gpt-4o")
    assert isinstance(p3, OpenAICompatibleProvider)
    assert p3.model == "gpt-4o"

    custom = MockCustomProvider()
    p4 = get_provider(custom)
    assert p4 is custom


def test_provider_health_checks():
    # Test checking connection on local provider when offline
    p_ollama = OllamaProvider(base_url="http://invalid-host-9999:11434")
    assert p_ollama.check_connection() is False

    # Test custom mock provider
    custom = MockCustomProvider()
    assert check_provider_health(custom) is True
