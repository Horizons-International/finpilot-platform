from collections.abc import AsyncIterator

from app.ai.providers.async_factory import get_async_ai_provider
from app.ai.services.async_ai_service import AsyncAIService


async def get_async_ai_service() -> AsyncIterator[AsyncAIService]:
    """Yield an async AI service and close its HTTP client after the request."""
    async with AsyncAIService(provider=get_async_ai_provider()) as service:
        yield service
