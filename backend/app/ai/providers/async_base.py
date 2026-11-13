from abc import ABC, abstractmethod

from app.ai.schemas.requests import AIRequest
from app.ai.schemas.responses import AIResponse


class AsyncAIProvider(ABC):
    """Asynchronous interface implemented by AI provider adapters."""

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """Generate a response without blocking the event loop."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release provider resources. Providers without resources may do nothing."""
        return None
