import uuid

import pytest
from pydantic import ValidationError

from app.ai.config import get_ai_config
from app.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIResponseError,
)
from app.ai.providers.base import AIProvider
from app.ai.providers.factory import get_ai_provider
from app.ai.providers.mock import MockAIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.schemas.responses import AIResponse
from app.ai.services.ai_service import AIService
from app.core.config import settings


def test_mock_provider_handles_text_request():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config=config)

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="Summarize this customer.",
    )

    response = provider.generate(request)

    assert response.provider_name == "mock"
    assert response.request_type == "text"
    assert response.content == ("Mock AI response for: Summarize this customer.")
    assert response.structured_data is None
    assert response.request_id is not None


def test_mock_provider_handles_document_analysis():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config=config)

    document_id = uuid.uuid4()

    request = AIRequest(
        request_type=AIRequestType.DOCUMENT_ANALYSIS,
        prompt="Analyze this identity document.",
        document_id=document_id,
        structured=True,
    )

    response = provider.generate(request)

    assert response.provider_name == "mock"
    assert response.request_type == "document_analysis"
    assert response.content == "Mock document analysis completed."
    assert response.request_id is not None

    assert response.structured_data is not None
    assert response.structured_data["document_id"] == str(document_id)
    assert response.structured_data["document_type"] == "unknown"


def test_mock_provider_rejects_empty_prompt():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config=config)

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="   ",
    )

    with pytest.raises(AIProviderError) as exc_info:
        provider.generate(request)

    assert str(exc_info.value) == "AI prompt cannot be empty."


def test_mock_provider_requires_document_id():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config=config)

    request = AIRequest(
        request_type=AIRequestType.DOCUMENT_ANALYSIS,
        prompt="Analyze this document.",
        document_id=None,
    )

    with pytest.raises(AIProviderError) as exc_info:
        provider.generate(request)

    assert str(exc_info.value) == ("Document ID is required for document analysis.")


def test_ai_service_returns_provider_response():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config=config)
    service = AIService(provider=provider)

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="Hello AI.",
    )

    response = service.generate(request)

    assert response.provider_name == "mock"
    assert response.request_type == "text"
    assert response.content == "Mock AI response for: Hello AI."
    assert response.request_id is not None


class FakeAIProvider(AIProvider):
    def __init__(self):
        self.request = None

    def generate(self, request: AIRequest) -> AIResponse:
        self.request = request

        return AIResponse(
            provider_name="fake",
            request_type=request.request_type.value,
            content="Fake provider response.",
            structured_data={
                "result": "success",
            },
            request_id=uuid.uuid4(),
        )


def test_ai_service_uses_provider_adapter():
    provider = FakeAIProvider()
    service = AIService(provider=provider)

    customer_id = uuid.uuid4()

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="Analyze customer.",
        customer_id=customer_id,
        structured=True,
    )

    response = service.generate(request)

    assert provider.request is not None
    assert provider.request.customer_id == customer_id
    assert provider.request.prompt == "Analyze customer."
    assert provider.request.structured is True

    assert response.provider_name == "fake"
    assert response.content == "Fake provider response."
    assert response.structured_data == {
        "result": "success",
    }


class FailingAIProvider(AIProvider):
    def generate(self, request: AIRequest) -> AIResponse:
        raise AIProviderError("Provider unavailable.")


def test_ai_service_propagates_provider_error():
    service = AIService(
        provider=FailingAIProvider(),
    )

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="Test request.",
    )

    with pytest.raises(AIProviderError) as exc_info:
        service.generate(request)

    assert str(exc_info.value) == "Provider unavailable."


class EmptyResponseAIProvider(AIProvider):
    def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            provider_name="fake",
            request_type=request.request_type.value,
            content="",
        )


def test_ai_service_rejects_empty_provider_response():
    service = AIService(
        provider=EmptyResponseAIProvider(),
    )

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="Test request.",
    )

    with pytest.raises(AIResponseError) as exc_info:
        service.generate(request)

    assert str(exc_info.value) == ("AI provider returned an empty response.")


class UnexpectedErrorProvider(AIProvider):
    def generate(self, request: AIRequest) -> AIResponse:
        raise RuntimeError("Unexpected failure.")


def test_ai_service_converts_unexpected_provider_error():
    service = AIService(
        provider=UnexpectedErrorProvider(),
    )

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="Test request.",
    )

    with pytest.raises(AIProviderError) as exc_info:
        service.generate(request)

    assert str(exc_info.value) == "AI provider request failed."


def test_ai_response_supports_structured_data():
    response = AIResponse(
        provider_name="fake",
        request_type="document_analysis",
        content="Analysis completed.",
        structured_data={
            "document_type": "passport",
            "confidence": 0.98,
            "valid": True,
        },
    )

    assert response.structured_data is not None
    assert response.structured_data["document_type"] == "passport"
    assert response.structured_data["confidence"] == 0.98
    assert response.structured_data["valid"] is True


def test_ai_request_supports_document_analysis():
    document_id = uuid.uuid4()

    request = AIRequest(
        request_type=AIRequestType.DOCUMENT_ANALYSIS,
        prompt="Analyze document.",
        document_id=document_id,
        structured=True,
    )

    assert request.request_type == AIRequestType.DOCUMENT_ANALYSIS
    assert request.document_id == document_id
    assert request.structured is True


def test_ai_provider_factory_returns_mock_provider():
    provider = get_ai_provider()

    assert isinstance(provider, MockAIProvider)


def test_ai_provider_factory_rejects_unsupported_provider(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "unsupported-provider",
    )

    with pytest.raises(AIConfigurationError) as exc_info:
        get_ai_provider()

    assert str(exc_info.value) == ("Unsupported AI provider: unsupported-provider")


def test_ai_configuration_loads():
    config = get_ai_config()

    assert config.provider == settings.AI_PROVIDER
    assert config.api_key == settings.AI_API_KEY
    assert config.model == settings.AI_MODEL
    assert config.max_tokens == settings.AI_MAX_TOKENS
    assert config.temperature == settings.AI_TEMPERATURE
    assert config.timeout == settings.AI_TIMEOUT


def test_ai_configuration_rejects_invalid_max_tokens():
    with pytest.raises(ValidationError):
        AIConfig(
            provider="mock",
            max_tokens=0,
        )


def test_ai_configuration_rejects_invalid_temperature():
    with pytest.raises(ValidationError):
        AIConfig(
            provider="mock",
            temperature=3.0,
        )


def test_ai_configuration_rejects_invalid_timeout():
    with pytest.raises(ValidationError):
        AIConfig(
            provider="mock",
            timeout=0,
        )


def test_ai_provider_uses_config():
    config = get_ai_config()
    provider = get_ai_provider()

    assert isinstance(provider, MockAIProvider)
    assert provider.config.provider == config.provider
    assert provider.config.model == config.model
    assert provider.config.max_tokens == config.max_tokens
    assert provider.config.temperature == config.temperature
    assert provider.config.timeout == config.timeout
