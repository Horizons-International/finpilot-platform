from app.ai.schemas.config import AIConfig
from app.core.config import settings


def get_ai_config() -> AIConfig:
    return AIConfig(
        provider=settings.AI_PROVIDER,
        api_key=settings.AI_API_KEY,
        model=settings.AI_MODEL,
        max_tokens=settings.AI_MAX_TOKENS,
        temperature=settings.AI_TEMPERATURE,
        timeout=settings.AI_TIMEOUT,
    )
