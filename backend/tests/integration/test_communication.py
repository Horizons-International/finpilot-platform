from uuid import uuid4

from app.communication.providers.base import EmailProvider, SMSProvider
from app.communication.providers.mock import (
    MockEmailProvider,
    MockSMSProvider,
)
from app.communication.schemas import (
    CommunicationProviderResult,
    EmailMessage,
    SMSMessage,
)
from app.models.communication_log import CommunicationLog
from app.services.communication_service import CommunicationService
from app.utils.enums import CommunicationChannel, CommunicationStatus


class FailingEmailProvider(EmailProvider):
    def send(
        self,
        message: EmailMessage,
    ) -> CommunicationProviderResult:
        raise RuntimeError("SMTP connection failed.")


class FailingSMSProvider(SMSProvider):
    def send(
        self,
        message: SMSMessage,
    ) -> CommunicationProviderResult:
        raise RuntimeError("SMS provider unavailable.")


def test_email_can_be_triggered(
    db_session,
    cleanup_communication_logs,
):
    service = CommunicationService(
        db=db_session,
        email_provider=MockEmailProvider(),
        sms_provider=MockSMSProvider(),
    )

    communication = service.send_email(
        recipient="customer@example.com",
        subject="Account created",
        body="Your account has been created.",
    )

    assert communication.id is not None
    assert communication.recipient == "customer@example.com"
    assert communication.channel == CommunicationChannel.EMAIL
    assert communication.status == CommunicationStatus.SENT
    assert communication.sent_at is not None
    assert communication.error_message is None


def test_sms_can_be_triggered(
    db_session,
    cleanup_communication_logs,
):
    service = CommunicationService(
        db=db_session,
        email_provider=MockEmailProvider(),
        sms_provider=MockSMSProvider(),
    )

    communication = service.send_sms(
        recipient="+249912345678",
        body="Your verification has started.",
    )

    assert communication.id is not None
    assert communication.recipient == "+249912345678"
    assert communication.channel == CommunicationChannel.SMS
    assert communication.status == CommunicationStatus.SENT
    assert communication.sent_at is not None
    assert communication.error_message is None


def test_communication_history_is_stored(
    db_session,
    cleanup_communication_logs,
):
    service = CommunicationService(
        db=db_session,
        email_provider=MockEmailProvider(),
        sms_provider=MockSMSProvider(),
    )

    communication = service.send_email(
        recipient="history@example.com",
        subject="History test",
        body="History message.",
        template_id=uuid4(),
    )

    db_session.expire_all()

    saved = (
        db_session.query(CommunicationLog)
        .filter(
            CommunicationLog.id == communication.id,
        )
        .first()
    )

    assert saved is not None
    assert saved.status == CommunicationStatus.SENT
    assert saved.template_id == communication.template_id


def test_failed_email_is_logged(
    db_session,
    cleanup_communication_logs,
):
    service = CommunicationService(
        db=db_session,
        email_provider=FailingEmailProvider(),
        sms_provider=MockSMSProvider(),
    )

    communication = service.send_email(
        recipient="failed@example.com",
        subject="Failure test",
        body="This should fail.",
    )

    assert communication.status == CommunicationStatus.FAILED
    assert communication.sent_at is None
    assert communication.error_message == "SMTP connection failed."

    saved = (
        db_session.query(CommunicationLog)
        .filter(
            CommunicationLog.id == communication.id,
        )
        .first()
    )

    assert saved is not None
    assert saved.status == CommunicationStatus.FAILED


def test_failed_sms_is_logged(
    db_session,
    cleanup_communication_logs,
):
    service = CommunicationService(
        db=db_session,
        email_provider=MockEmailProvider(),
        sms_provider=FailingSMSProvider(),
    )

    communication = service.send_sms(
        recipient="+249912345678",
        body="This should fail.",
    )

    assert communication.status == CommunicationStatus.FAILED
    assert communication.sent_at is None
    assert communication.error_message == "SMS provider unavailable."


def test_delivery_status_can_be_updated(
    db_session,
    cleanup_communication_logs,
):
    service = CommunicationService(
        db=db_session,
        email_provider=MockEmailProvider(),
        sms_provider=MockSMSProvider(),
    )

    communication = service.send_email(
        recipient="delivery@example.com",
        subject="Delivery test",
        body="Delivery test.",
    )

    updated = service.update_delivery_status(
        communication_id=communication.id,
        status=CommunicationStatus.DELIVERED,
    )

    assert updated.status == CommunicationStatus.DELIVERED
    assert updated.sent_at is not None
    assert updated.error_message is None
