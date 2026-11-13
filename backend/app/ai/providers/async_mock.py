from app.ai.providers.async_base import AsyncAIProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest
from app.ai.schemas.responses import AIResponse


class AsyncMockAIProvider(AsyncAIProvider):
    """Async adapter for the deterministic, local mock provider."""

    def __init__(self, config: AIConfig) -> None:
        self.config = config
        self._provider = MockAIProvider(config=config)

    async def generate(self, request: AIRequest) -> AIResponse:
        # The mock provider performs local deterministic work only; it has no
        # network or filesystem I/O to offload.
        return self._provider.generate(request)
