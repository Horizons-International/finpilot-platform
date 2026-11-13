from app.ai.config import get_ai_config
from app.ai.exceptions import AIConfigurationError
from app.ai.providers.async_base import AsyncAIProvider
from app.ai.providers.async_mock import AsyncMockAIProvider
from app.ai.providers.async_openai import AsyncOpenAIProvider


def get_async_ai_provider() -> AsyncAIProvider:
    """Return the asynchronous provider selected by the application config."""
    config = get_ai_config()
    provider_name = config.provider.lower()

    if provider_name == "mock":
        return AsyncMockAIProvider(config=config)
    if provider_name == "openai":
        return AsyncOpenAIProvider(config=config)

    raise AIConfigurationError(f"Unsupported AI provider: {config.provider}")
