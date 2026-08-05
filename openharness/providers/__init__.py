from typing import Optional, Union, Dict
from openharness.providers.base import BaseProvider, ProviderResponse
from openharness.providers.local_ollama import OllamaProvider
from openharness.providers.openai_compatible import OpenAICompatibleProvider


def get_provider(model_identifier: Union[str, BaseProvider]) -> BaseProvider:
    """
    Factory to resolve model identifier string into a BaseProvider instance.

    Examples:
        - "ollama/llama3.1" -> OllamaProvider(model="llama3.1")
        - "vllm/qwen2.5" -> OpenAICompatibleProvider(model="qwen2.5", base_url="http://localhost:8000/v1")
        - "openai/gpt-4o" -> OpenAICompatibleProvider(model="gpt-4o")
        - "gpt-4o-mini" -> OpenAICompatibleProvider(model="gpt-4o-mini")
    """
    if isinstance(model_identifier, BaseProvider):
        return model_identifier

    model_str = str(model_identifier).strip()

    if model_str.startswith("ollama/") or "11434" in model_str:
        model_name = model_str.replace("ollama/", "")
        return OllamaProvider(model=model_name)
    elif model_str.startswith("vllm/"):
        model_name = model_str.replace("vllm/", "")
        return OpenAICompatibleProvider(model=model_name, base_url="http://localhost:8000/v1")
    elif model_str.startswith("openai/"):
        model_name = model_str.replace("openai/", "")
        return OpenAICompatibleProvider(model=model_name)
    else:
        return OpenAICompatibleProvider(model=model_str)


def check_provider_health(model_identifier: Union[str, BaseProvider]) -> bool:
    """Verify endpoint connectivity and model status for a provider."""
    provider = get_provider(model_identifier)
    return provider.check_connection()


__all__ = [
    "BaseProvider",
    "ProviderResponse",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "get_provider",
    "check_provider_health"
]
