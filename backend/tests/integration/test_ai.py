from uuid import UUID

import pytest

from app.ai.exceptions import AIProviderError
from app.ai.providers.mock import MockAIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.utils.strings import truncate_text


def test_mock_provider_accepts_text_request():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config)

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="Hello AI.",
    )

    response = provider.generate(request)

    assert response.provider_name == "mock"
    assert response.request_type == "text"
    assert response.content == "Mock AI response for: Hello AI."
    assert response.structured_data is None
    assert response.request_id is not None


def test_mock_provider_accepts_document_analysis_request():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config)

    request = AIRequest(
        request_type=AIRequestType.DOCUMENT_ANALYSIS,
        prompt="Analyze this document.",
        document_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    response = provider.generate(request)

    assert response.provider_name == "mock"
    assert response.request_type == "document_analysis"
    assert response.content == "Mock document analysis completed."
    assert response.structured_data is not None
    assert response.structured_data["document_id"] == (
        "00000000-0000-0000-0000-000000000001"
    )
    assert response.structured_data["document_type"] == "unknown"
    assert response.structured_data["confidence"] == 0.0
    assert response.request_id is not None


def test_mock_provider_accepts_compliance_assistant_request():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config)

    request = AIRequest(
        request_type=AIRequestType.COMPLIANCE_ASSISTANT,
        prompt="Summarize this customer's verification status.",
        structured=True,
    )

    response = provider.generate(request)

    assert response.provider_name == "mock"
    assert response.request_type == "compliance_assistant"
    assert response.content == "Mock compliance assistant response."
    assert response.structured_data is not None

    assert response.structured_data["summary"] == ("Mock compliance summary.")
    assert response.structured_data["customer_status"] == "Pending"
    assert response.structured_data["missing_documents"] == []
    assert response.structured_data["findings"] == []
    assert response.structured_data["recommendation"] == (
        "Review the available compliance information."
    )
    assert response.structured_data["confidence"] == 0.0
    assert response.request_id is not None


def test_mock_provider_rejects_empty_prompt():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config)

    request = AIRequest(
        request_type=AIRequestType.TEXT,
        prompt="   ",
    )

    with pytest.raises(AIProviderError, match="AI prompt cannot be empty."):
        provider.generate(request)


def test_mock_provider_requires_document_id_for_document_analysis():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config)

    request = AIRequest(
        request_type=AIRequestType.DOCUMENT_ANALYSIS,
        prompt="Analyze this document.",
    )

    with pytest.raises(
        AIProviderError,
        match="Document ID is required for document analysis.",
    ):
        provider.generate(request)


def test_mock_provider_rejects_unsupported_request_type():
    config = AIConfig(provider="mock")

    provider = MockAIProvider(config)

    request = AIRequest(
        request_type="unsupported",
        prompt="Test prompt.",
    )

    with pytest.raises(
        AIProviderError,
        match="Unsupported AI request type",
    ):
        provider.generate(request)


def test_truncate_text_returns_none_for_none():
    assert truncate_text(None, 10) is None


def test_truncate_text_returns_short_text_unchanged():
    value = "Hello"

    assert truncate_text(value, 10) == value


def test_truncate_text_does_not_truncate_exact_length():
    value = "1234567890"

    assert truncate_text(value, 10) == value


def test_truncate_text_truncates_long_text():
    value = "abcdefghijklmnopqrstuvwxyz"

    result = truncate_text(value, 10)

    assert result == "abcdefghij\n[TRUNCATED]"


def test_truncate_text_preserves_original_prefix():
    value = "abcdefghijklmnopqrstuvwxyz"

    result = truncate_text(value, 10)

    assert result is not None
    assert result.startswith(value[:10])
    assert result.endswith("\n[TRUNCATED]")
