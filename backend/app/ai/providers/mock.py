import uuid

from app.ai.exceptions import AIProviderError
from app.ai.providers.base import AIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.schemas.responses import AIResponse


class MockAIProvider(AIProvider):
    def __init__(self, config: AIConfig) -> None:
        self.config = config

    def generate(self, request: AIRequest) -> AIResponse:
        if not request.prompt.strip():
            raise AIProviderError("AI prompt cannot be empty.")

        if request.request_type == AIRequestType.TEXT:
            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content=f"Mock AI response for: {request.prompt}",
                request_id=uuid.uuid4(),
            )

        if request.request_type == AIRequestType.DOCUMENT_ANALYSIS:
            if request.document_id is None:
                raise AIProviderError("Document ID is required for document analysis.")

            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content="Mock document analysis completed.",
                structured_data={
                    "document_id": str(request.document_id),
                    "document_type": "unknown",
                    "confidence": 0.0,
                },
                request_id=uuid.uuid4(),
            )

        raise AIProviderError(f"Unsupported AI request type: {request.request_type}")
