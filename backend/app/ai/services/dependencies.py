from app.ai.providers.base import AIProvider
from app.ai.providers.factory import get_ai_provider
from app.ai.services.ai_service import AIService


def get_ai_service() -> AIService:
    provider: AIProvider = get_ai_provider()

    return AIService(provider=provider)
