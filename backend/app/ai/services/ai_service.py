from app.ai.exceptions import (
    AIProviderError,
    AIResponseError,
)
from app.ai.providers.base import AIProvider
from app.ai.schemas.requests import AIRequest
from app.ai.schemas.responses import AIResponse
from app.core.logger import get_logger

logger = get_logger(__name__)


class AIService:
    """Centralized service for AI operations."""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def generate(self, request: AIRequest) -> AIResponse:
        logger.info(
            "AI request started: provider=%s request_type=%s "
            "customer_id=%s document_id=%s structured=%s",
            self.provider.__class__.__name__,
            request.request_type.value,
            request.customer_id,
            request.document_id,
            request.structured,
        )

        try:
            response = self.provider.generate(request)
        except AIProviderError:
            logger.exception(
                "AI provider failed: provider=%s request_type=%s",
                self.provider.__class__.__name__,
                request.request_type.value,
            )
            raise
        except Exception as exc:
            logger.exception(
                "Unexpected AI provider error: provider=%s request_type=%s",
                self.provider.__class__.__name__,
                request.request_type.value,
            )
            raise AIProviderError("AI provider request failed.") from exc

        if not response.content:
            logger.error(
                "AI provider returned an empty response: provider=%s",
                self.provider.__class__.__name__,
            )
            raise AIResponseError("AI provider returned an empty response.")

        logger.info(
            "AI request completed: provider=%s request_type=%s request_id=%s",
            response.provider_name,
            response.request_type,
            response.request_id,
        )

        return response
