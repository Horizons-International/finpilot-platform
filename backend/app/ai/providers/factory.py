from app.ai.exceptions import AIConfigurationError
from app.ai.providers.base import AIProvider
from app.ai.providers.mock import MockAIProvider
from app.core.config import settings


def get_ai_provider() -> AIProvider:
    """Return the configured AI provider."""

    provider_name = settings.AI_PROVIDER.lower()

    if provider_name == "mock":
        return MockAIProvider()

    raise AIConfigurationError(f"Unsupported AI provider: {settings.AI_PROVIDER}")
