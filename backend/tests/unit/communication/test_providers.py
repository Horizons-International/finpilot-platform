from app.communication.providers.mock import (
    MockEmailProvider,
    MockSMSProvider,
)
from app.communication.schemas import EmailMessage, SMSMessage
from app.utils.enums import CommunicationStatus


def test_mock_email_provider_sends_email():
    provider = MockEmailProvider()

    result = provider.send(
        EmailMessage(
            recipient="user@example.com",
            subject="Test email",
            body="Test email body.",
        )
    )

    assert result.status == CommunicationStatus.SENT
    assert result.sent_at is not None


def test_mock_sms_provider_sends_sms():
    provider = MockSMSProvider()

    result = provider.send(
        SMSMessage(
            recipient="+249912345678",
            body="Test SMS.",
        )
    )

    assert result.status == CommunicationStatus.SENT
    assert result.sent_at is not None
