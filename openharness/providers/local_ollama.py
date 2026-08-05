import httpx
from typing import Optional, Dict, Any
from openharness.providers.base import BaseProvider, ProviderResponse


class OllamaProvider(BaseProvider):
    """Local Ollama provider with KV prompt caching & adaptive effort budgeting."""

    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def check_connection(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        use_cache: bool = True,
        effort: str = "low",
        **kwargs
    ) -> ProviderResponse:
        url = f"{self.base_url}/api/generate"
        
        # Adaptive effort token limit
        token_limit = 250 if effort == "low" else max_tokens

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "15m" if use_cache else "0m",  # Retain KV prompt context in GPU/RAM
            "options": {
                "temperature": temperature,
                "num_predict": token_limit
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                prompt_tokens = data.get("prompt_eval_count", 0)
                eval_tokens = data.get("eval_count", 0)
                # Estimate cached tokens if keep_alive hit
                cached_tokens = prompt_tokens if use_cache else 0
                return ProviderResponse(
                    content=data.get("response", ""),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=eval_tokens,
                    cached_tokens=cached_tokens,
                    model=self.model,
                    metadata={"provider": "ollama", "keep_alive": "15m", "effort": effort}
                )
        except Exception as e:
            raise RuntimeError(f"Ollama generation failed ({self.base_url}, model={self.model}): {str(e)}") from e

    async def agenerate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        use_cache: bool = True,
        effort: str = "low",
        **kwargs
    ) -> ProviderResponse:
        url = f"{self.base_url}/api/generate"
        token_limit = 250 if effort == "low" else max_tokens

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "15m" if use_cache else "0m",
            "options": {
                "temperature": temperature,
                "num_predict": token_limit
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                prompt_tokens = data.get("prompt_eval_count", 0)
                eval_tokens = data.get("eval_count", 0)
                cached_tokens = prompt_tokens if use_cache else 0
                return ProviderResponse(
                    content=data.get("response", ""),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=eval_tokens,
                    cached_tokens=cached_tokens,
                    model=self.model,
                    metadata={"provider": "ollama", "keep_alive": "15m", "effort": effort}
                )
        except Exception as e:
            raise RuntimeError(f"Ollama async generation failed ({self.base_url}, model={self.model}): {str(e)}") from e
