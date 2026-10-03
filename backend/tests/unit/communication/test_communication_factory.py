import pytest

from app.communication.exceptions import CommunicationConfigurationError
from app.communication.providers.factory import (
    get_email_provider,
    get_sms_provider,
)
from app.communication.providers.mock import (
    MockEmailProvider,
    MockSMSProvider,
)


def test_email_factory_returns_mock_provider():
    provider = get_email_provider()

    assert isinstance(provider, MockEmailProvider)


def test_sms_factory_returns_mock_provider():
    provider = get_sms_provider()

    assert isinstance(provider, MockSMSProvider)


def test_email_factory_rejects_unknown_provider(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(
        settings,
        "EMAIL_PROVIDER",
        "unknown",
    )

    with pytest.raises(CommunicationConfigurationError):
        get_email_provider()


def test_sms_factory_rejects_unknown_provider(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(
        settings,
        "SMS_PROVIDER",
        "unknown",
    )

    with pytest.raises(CommunicationConfigurationError):
        get_sms_provider()
