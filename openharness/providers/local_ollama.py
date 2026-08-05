import httpx
from typing import Optional, Dict, Any
from openharness.providers.base import BaseProvider, ProviderResponse


class OllamaProvider(BaseProvider):
    """Local Ollama provider for zero-cost LLM generation and judging."""

    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs
    ) -> ProviderResponse:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return ProviderResponse(
                    content=data.get("response", ""),
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    model=self.model,
                    metadata={"provider": "ollama", "done_reason": data.get("done_reason")}
                )
        except Exception as e:
            # Fallback or informative error
            raise RuntimeError(f"Ollama generation failed ({self.base_url}, model={self.model}): {str(e)}") from e

    async def agenerate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs
    ) -> ProviderResponse:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return ProviderResponse(
                    content=data.get("response", ""),
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    model=self.model,
                    metadata={"provider": "ollama", "done_reason": data.get("done_reason")}
                )
        except Exception as e:
            raise RuntimeError(f"Ollama async generation failed ({self.base_url}, model={self.model}): {str(e)}") from e
