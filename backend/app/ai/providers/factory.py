from app.ai.config import get_ai_config
from app.ai.exceptions import AIConfigurationError
from app.ai.providers.base import AIProvider
from app.ai.providers.mock import MockAIProvider


def get_ai_provider() -> AIProvider:
    """Return the configured AI provider."""

    config = get_ai_config()

    provider_name = config.provider.lower()

    if provider_name == "mock":
        return MockAIProvider(config=config)

    raise AIConfigurationError(f"Unsupported AI provider: {config.provider}")
