from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.core.config import settings
from app.rag import embeddings
from app.rag.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EmbeddingService,
)


class FakeEmbeddingsClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeOpenAIClient:
    def __init__(self, response):
        self.embeddings = FakeEmbeddingsClient(response)


def make_embedding(value: float) -> list[float]:
    return [value] * EMBEDDING_DIMENSIONS


def test_embedding_service_requires_openai_provider(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "mock",
    )

    with pytest.raises(AIConfigurationError, match="OpenAI provider"):
        EmbeddingService()


def test_embedding_service_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "",
    )

    with pytest.raises(
        AIConfigurationError,
        match="AI_API_KEY is required",
    ):
        EmbeddingService()


def test_embedding_service_initializes_openai_client(monkeypatch):
    fake_client = object()

    def fake_openai(**kwargs):
        assert kwargs["api_key"] == "test-key"
        return fake_client

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        fake_openai,
    )

    service = EmbeddingService()

    assert service.client is fake_client


def test_embed_rejects_empty_text(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )

    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: object(),
    )

    service = EmbeddingService()

    with pytest.raises(
        ValueError,
        match="empty text",
    ):
        service.embed("")


def test_embed_rejects_whitespace_only_text(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )

    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: object(),
    )

    service = EmbeddingService()

    with pytest.raises(
        ValueError,
        match="empty text",
    ):
        service.embed("   ")


def test_embed_returns_embedding(monkeypatch):
    expected_embedding = make_embedding(0.25)

    response = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=expected_embedding,
            )
        ]
    )

    fake_client = FakeOpenAIClient(response)

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: fake_client,
    )

    service = EmbeddingService()

    result = service.embed("What is our compliance policy?")

    assert result == expected_embedding

    assert fake_client.embeddings.calls == [
        {
            "model": EMBEDDING_MODEL,
            "input": "What is our compliance policy?",
        }
    ]


def test_embed_wraps_provider_error(monkeypatch):
    class FailingEmbeddings:
        def create(self, **kwargs):
            raise RuntimeError("Provider failure")

    class FailingClient:
        embeddings = FailingEmbeddings()

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: FailingClient(),
    )

    service = EmbeddingService()

    with pytest.raises(
        AIProviderError,
        match="Failed to generate text embedding",
    ):
        service.embed("Some text")


def test_embed_rejects_empty_provider_response(monkeypatch):
    response = SimpleNamespace(data=[])

    fake_client = FakeOpenAIClient(response)

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: fake_client,
    )

    service = EmbeddingService()

    with pytest.raises(
        AIProviderError,
        match="no data",
    ):
        service.embed("Some text")


def test_embed_rejects_wrong_embedding_dimension(monkeypatch):
    response = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=[0.1, 0.2],
            )
        ]
    )

    fake_client = FakeOpenAIClient(response)

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: fake_client,
    )

    service = EmbeddingService()

    with pytest.raises(
        AIProviderError,
        match="dimension",
    ):
        service.embed("Some text")


def test_embed_many_rejects_empty_list(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: object(),
    )

    service = EmbeddingService()

    assert service.embed_many([]) == []


def test_embed_many_rejects_empty_text(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: object(),
    )

    service = EmbeddingService()

    with pytest.raises(
        ValueError,
        match="empty text",
    ):
        service.embed_many(
            [
                "Valid text",
                "",
            ]
        )


def test_embed_many_returns_embeddings_in_input_order(monkeypatch):
    first_embedding = make_embedding(0.1)
    second_embedding = make_embedding(0.2)

    response = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=1,
                embedding=second_embedding,
            ),
            SimpleNamespace(
                index=0,
                embedding=first_embedding,
            ),
        ]
    )

    fake_client = FakeOpenAIClient(response)

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: fake_client,
    )

    service = EmbeddingService()

    result = service.embed_many(
        [
            "First document chunk",
            "Second document chunk",
        ]
    )

    assert result == [
        first_embedding,
        second_embedding,
    ]


def test_embed_many_rejects_unexpected_embedding_count(monkeypatch):
    response = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=make_embedding(0.1),
            )
        ]
    )

    fake_client = FakeOpenAIClient(response)

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: fake_client,
    )

    service = EmbeddingService()

    with pytest.raises(
        AIProviderError,
        match="unexpected number",
    ):
        service.embed_many(
            [
                "First",
                "Second",
            ]
        )


def test_embed_many_rejects_wrong_embedding_dimension(monkeypatch):
    response = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=[0.1, 0.2],
            ),
            SimpleNamespace(
                index=1,
                embedding=make_embedding(0.2),
            ),
        ]
    )

    fake_client = FakeOpenAIClient(response)

    monkeypatch.setattr(
        settings,
        "AI_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "AI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        lambda **_: fake_client,
    )

    service = EmbeddingService()

    with pytest.raises(
        AIProviderError,
        match="dimension",
    ):
        service.embed_many(
            [
                "First",
                "Second",
            ]
        )


def test_embed_query_delegates_to_embed():
    service = object.__new__(EmbeddingService)

    expected_embedding = [0.1] * EMBEDDING_DIMENSIONS

    with patch.object(
        service,
        "embed",
        return_value=expected_embedding,
    ) as mock_embed:
        result = service.embed_query("What is the customer verification policy?")

    assert result == expected_embedding

    mock_embed.assert_called_once_with("What is the customer verification policy?")


def test_embed_query_rejects_empty_query():
    service = object.__new__(EmbeddingService)

    with pytest.raises(
        ValueError,
        match="Cannot generate an embedding for an empty query.",
    ):
        service.embed_query("")


def test_embed_query_rejects_whitespace_query():
    service = object.__new__(EmbeddingService)

    with pytest.raises(
        ValueError,
        match="Cannot generate an embedding for an empty query.",
    ):
        service.embed_query("   ")
