import pytest

from app.core.config import settings
from app.providers.factory import get_verification_provider
from app.providers.mock_provider import MockVerificationProvider


def test_factory_returns_mock_provider(monkeypatch):
    monkeypatch.setattr(
        settings,
        "VERIFICATION_PROVIDER",
        "mock",
    )

    provider = get_verification_provider()

    assert isinstance(provider, MockVerificationProvider)


def test_factory_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr(
        settings,
        "VERIFICATION_PROVIDER",
        "unsupported",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported verification provider",
    ):
        get_verification_provider()
