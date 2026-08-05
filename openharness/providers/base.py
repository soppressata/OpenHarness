from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ProviderResponse(BaseModel):
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    model: str
    metadata: Dict[str, Any] = {}


class BaseProvider(ABC):
    """Abstract Base Provider for LLM calls with Prompt Caching & Adaptive Effort Control."""

    @abstractmethod
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
        """Generate response from the model synchronously."""
        pass

    @abstractmethod
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
        """Generate response from the model asynchronously."""
        pass

    @abstractmethod
    def check_connection(self) -> bool:
        """Verify endpoint connectivity and model availability."""
        pass
