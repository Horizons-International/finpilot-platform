import asyncio
import json
from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.providers.async_factory import get_async_ai_provider
from app.ai.providers.async_mock import AsyncMockAIProvider
from app.ai.providers.async_openai import AsyncOpenAIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.async_ai_service import AsyncAIService


class _FakeResponses:
    def __init__(self, content: str) -> None:
        self.content = content
        self.request: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(
            output_text=self.content,
            usage=SimpleNamespace(input_tokens=12, output_tokens=7),
        )


class _FakeAsyncOpenAI:
    def __init__(self, content: str) -> None:
        self.responses = _FakeResponses(content)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_async_mock_provider_implements_async_contract() -> None:
    provider = AsyncMockAIProvider(AIConfig(provider="mock"))
    request = AIRequest(request_type=AIRequestType.TEXT, prompt="Hello")

    response = asyncio.run(provider.generate(request))

    assert response.provider_name == "mock"
    assert response.content == "Mock AI response for: Hello"


def test_async_openai_provider_parses_structured_response_and_closes_client() -> None:
    payload = {
        "summary": "Review completed.",
        "customer_status": "Pending",
        "missing_documents": [],
        "findings": [],
        "recommendation": "Continue review.",
        "confidence": 0.8,
    }
    fake_client = _FakeAsyncOpenAI(json.dumps(payload))
    provider = AsyncOpenAIProvider(
        AIConfig(provider="openai", api_key="test-key", model="test-model"),
        client=cast(AsyncOpenAI, fake_client),
    )
    request = AIRequest(
        request_type=AIRequestType.COMPLIANCE_ASSISTANT,
        prompt="Review the supplied compliance information.",
        structured=True,
    )

    async def run() -> None:
        async with AsyncAIService(provider) as service:
            response = await service.generate(request)
        assert fake_client.closed is True
        assert response.structured_data == payload
        assert response.input_tokens == 12
        assert response.output_tokens == 7

    asyncio.run(run())
    assert fake_client.responses.request is not None
    assert fake_client.responses.request["model"] == "test-model"


def test_async_openai_provider_rejects_missing_credentials() -> None:
    with pytest.raises(AIConfigurationError, match="AI_API_KEY is required"):
        AsyncOpenAIProvider(AIConfig(provider="openai", model="test-model"))


def test_async_openai_provider_rejects_empty_prompt() -> None:
    fake_client = _FakeAsyncOpenAI("{}")
    provider = AsyncOpenAIProvider(
        AIConfig(provider="openai", api_key="test-key", model="test"),
        client=cast(AsyncOpenAI, fake_client),
    )
    request = AIRequest(request_type=AIRequestType.COMPLIANCE_ASSISTANT, prompt=" ")

    with pytest.raises(AIProviderError, match="AI prompt cannot be empty"):
        asyncio.run(provider.generate(request))


def test_async_factory_returns_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.ai.providers.async_factory.get_ai_config",
        lambda: AIConfig(provider="mock"),
    )

    assert isinstance(get_async_ai_provider(), AsyncMockAIProvider)
