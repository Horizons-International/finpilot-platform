from app.communication.exceptions import CommunicationProviderError
from app.communication.providers.base import EmailProvider, SMSProvider
from app.communication.schemas import (
    CommunicationProviderResult,
    EmailMessage,
    SMSMessage,
)
from app.utils.date_time import utc_now
from app.utils.enums import CommunicationStatus


class MockEmailProvider(EmailProvider):
    def send(
        self,
        message: EmailMessage,
    ) -> CommunicationProviderResult:
        if not message.recipient.strip():
            raise CommunicationProviderError(
                "Email recipient is required.",
            )

        if not message.subject.strip():
            raise CommunicationProviderError(
                "Email subject is required.",
            )

        if not message.body.strip():
            raise CommunicationProviderError(
                "Email body is required.",
            )

        return CommunicationProviderResult(
            status=CommunicationStatus.SENT,
            sent_at=utc_now(),
        )


class MockSMSProvider(SMSProvider):
    def send(
        self,
        message: SMSMessage,
    ) -> CommunicationProviderResult:
        if not message.recipient.strip():
            raise CommunicationProviderError(
                "SMS recipient is required.",
            )

        if not message.body.strip():
            raise CommunicationProviderError(
                "SMS body is required.",
            )

        return CommunicationProviderResult(
            status=CommunicationStatus.SENT,
            sent_at=utc_now(),
        )
