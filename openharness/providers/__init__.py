from typing import Union, Optional
from openharness.providers.base import BaseProvider, ProviderResponse
from openharness.providers.local_ollama import OllamaProvider
from openharness.providers.openai_compatible import OpenAICompatibleProvider


def get_provider(provider_or_spec: Union[str, BaseProvider]) -> BaseProvider:
    """
    Factory to obtain a provider instance based on a spec string or custom BaseProvider.
    Examples:
        - "ollama/llama3.1"
        - "vllm/qwen2.5-coder"
        - "openai/gpt-4o"
        - "http://localhost:11434"
    """
    if isinstance(provider_or_spec, BaseProvider):
        return provider_or_spec

    spec = str(provider_or_spec).strip()
    
    if spec.startswith("ollama/"):
        model_name = spec.split("ollama/", 1)[1]
        return OllamaProvider(model=model_name)
    elif spec.startswith("vllm/"):
        model_name = spec.split("vllm/", 1)[1]
        return OpenAICompatibleProvider(model=model_name, base_url="http://localhost:8000/v1")
    elif spec.startswith("openai/"):
        model_name = spec.split("openai/", 1)[1]
        return OpenAICompatibleProvider(model=model_name)
    elif "localhost:11434" in spec or "127.0.0.1:11434" in spec:
        return OllamaProvider(base_url=spec)
    elif spec.startswith("http://") or spec.startswith("https://"):
        return OpenAICompatibleProvider(base_url=spec)
    else:
        return OllamaProvider(model=spec)


__all__ = ["BaseProvider", "ProviderResponse", "OllamaProvider", "OpenAICompatibleProvider", "get_provider"]
