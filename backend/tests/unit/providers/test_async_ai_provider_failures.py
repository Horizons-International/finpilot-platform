from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from app.ai.exceptions import AIProviderError
from app.ai.providers.async_base import AsyncAIProvider
from app.ai.providers.async_openai import AsyncOpenAIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.schemas.responses import AIResponse
from app.ai.services.async_ai_service import AsyncAIService


class FakeResponses:
    def __init__(self, output_text: str = "", error: Exception | None = None) -> None:
        self.output_text = output_text
        self.error = error

    async def create(self, **kwargs: object) -> SimpleNamespace:
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            output_text=self.output_text,
            usage=SimpleNamespace(input_tokens=3, output_tokens=5),
        )


class FakeAsyncOpenAI:
    def __init__(
        self, *, output_text: str = "", error: Exception | None = None
    ) -> None:
        self.responses = FakeResponses(output_text=output_text, error=error)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def make_request() -> AIRequest:
    return AIRequest(
        request_type=AIRequestType.COMPLIANCE_ASSISTANT,
        prompt="Review the supplied compliance evidence.",
        structured=True,
    )


def make_provider(client: FakeAsyncOpenAI) -> AsyncOpenAIProvider:
    return AsyncOpenAIProvider(
        AIConfig(provider="openai", api_key="test-key", model="test-model"),
        client=cast(AsyncOpenAI, client),
    )


def test_async_openai_provider_rejects_empty_response() -> None:
    provider = make_provider(FakeAsyncOpenAI(output_text=""))
    with pytest.raises(AIProviderError, match="empty response"):
        asyncio.run(provider.generate(make_request()))


def test_async_openai_provider_rejects_invalid_json() -> None:
    provider = make_provider(FakeAsyncOpenAI(output_text="not-json"))
    with pytest.raises(AIProviderError, match="invalid structured data"):
        asyncio.run(provider.generate(make_request()))


@pytest.mark.parametrize("output_text", ["[]", "null", '"not-an-object"'])
def test_async_openai_provider_rejects_non_object_json(output_text: str) -> None:
    provider = make_provider(FakeAsyncOpenAI(output_text=output_text))
    with pytest.raises(AIProviderError, match="invalid structured data"):
        asyncio.run(provider.generate(make_request()))


def test_async_openai_provider_wraps_api_errors() -> None:
    provider = make_provider(FakeAsyncOpenAI(error=RuntimeError("network failure")))
    with pytest.raises(AIProviderError, match="OpenAI provider request failed"):
        asyncio.run(provider.generate(make_request()))


def test_async_ai_service_closes_client_when_generation_fails() -> None:
    client = FakeAsyncOpenAI(error=RuntimeError("network failure"))
    provider = make_provider(client)

    async def run() -> None:
        with pytest.raises(AIProviderError, match="AI provider request failed"):
            async with AsyncAIService(provider) as service:
                await service.generate(make_request())

    asyncio.run(run())
    assert client.closed is True


def test_async_ai_service_wraps_unexpected_provider_errors() -> None:
    class UnexpectedProvider(AsyncAIProvider):
        async def generate(self, request: AIRequest) -> AIResponse:
            raise RuntimeError("unexpected provider failure")

    async def run() -> None:
        service = AsyncAIService(UnexpectedProvider())
        with pytest.raises(AIProviderError, match="AI provider request failed"):
            await service.generate(make_request())

    asyncio.run(run())


def test_async_openai_provider_rejects_unsupported_request_type() -> None:
    provider = make_provider(FakeAsyncOpenAI(output_text="{}"))
    request = AIRequest(request_type=AIRequestType.TEXT, prompt="Hello")
    with pytest.raises(AIProviderError, match="does not support this request type"):
        asyncio.run(provider.generate(request))
