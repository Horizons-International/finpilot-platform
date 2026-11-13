from types import TracebackType

from app.ai.exceptions import AIProviderError, AIResponseError
from app.ai.providers.async_base import AsyncAIProvider
from app.ai.schemas.requests import AIRequest
from app.ai.schemas.responses import AIResponse
from app.core.logger import get_logger

logger = get_logger(__name__)


class AsyncAIService:
    """Validate and execute AI requests through an asynchronous provider."""

    def __init__(self, provider: AsyncAIProvider) -> None:
        self.provider = provider

    async def generate(self, request: AIRequest) -> AIResponse:
        logger.info(
            "Async AI request started: provider=%s request_type=%s "
            "customer_id=%s document_id=%s structured=%s",
            self.provider.__class__.__name__,
            request.request_type.value,
            request.customer_id,
            request.document_id,
            request.structured,
        )
        try:
            response = await self.provider.generate(request)
        except AIProviderError:
            logger.exception(
                "Async AI provider failed: provider=%s request_type=%s",
                self.provider.__class__.__name__,
                request.request_type.value,
            )
            raise
        except Exception as exc:
            logger.exception(
                "Unexpected async AI provider error: provider=%s request_type=%s",
                self.provider.__class__.__name__,
                request.request_type.value,
            )
            raise AIProviderError("AI provider request failed.") from exc

        if not response.content:
            logger.error(
                "Async AI provider returned an empty response: provider=%s",
                self.provider.__class__.__name__,
            )
            raise AIResponseError("AI provider returned an empty response.")

        logger.info(
            "Async AI request completed: provider=%s request_type=%s request_id=%s",
            response.provider_name,
            response.request_type,
            response.request_id,
        )
        return response

    async def aclose(self) -> None:
        await self.provider.aclose()

    async def __aenter__(self) -> "AsyncAIService":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
