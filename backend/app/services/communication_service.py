from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.communication.providers.base import EmailProvider, SMSProvider
from app.communication.schemas import EmailMessage, SMSMessage
from app.models.communication_log import CommunicationLog
from app.repositories.communication_log_repository import (
    CommunicationLogRepository,
)
from app.utils.date_time import utc_now
from app.utils.enums import CommunicationChannel, CommunicationStatus
from app.utils.errors import bad_request, not_found
from app.utils.validators.email import validate_email
from app.utils.validators.phone import validate_phone


class CommunicationService:
    def __init__(
        self,
        db: Session,
        *,
        email_provider: EmailProvider,
        sms_provider: SMSProvider,
    ) -> None:
        self.db = db
        self.repository = CommunicationLogRepository(db)
        self.email_provider = email_provider
        self.sms_provider = sms_provider

    def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        template_id: UUID | None = None,
    ) -> CommunicationLog:
        try:
            normalized_recipient = validate_email(recipient)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        normalized_subject = subject.strip()
        normalized_body = body.strip()

        if not normalized_subject:
            raise bad_request(
                "Email subject is required.",
            )

        if not normalized_body:
            raise bad_request(
                "Email body is required.",
            )

        log = self._create_pending_log(
            recipient=normalized_recipient,
            channel=CommunicationChannel.EMAIL,
            template_id=template_id,
        )

        return self._send(
            log=log,
            sender=lambda: self.email_provider.send(
                EmailMessage(
                    recipient=normalized_recipient,
                    subject=normalized_subject,
                    body=normalized_body,
                )
            ),
        )

    def send_sms(
        self,
        *,
        recipient: str,
        body: str,
        template_id: UUID | None = None,
    ) -> CommunicationLog:
        try:
            normalized_recipient = validate_phone(recipient)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        normalized_body = body.strip()

        if not normalized_body:
            raise bad_request(
                "SMS message is required.",
            )

        log = self._create_pending_log(
            recipient=normalized_recipient,
            channel=CommunicationChannel.SMS,
            template_id=template_id,
        )

        return self._send(
            log=log,
            sender=lambda: self.sms_provider.send(
                SMSMessage(
                    recipient=normalized_recipient,
                    body=normalized_body,
                )
            ),
        )

    def get_communication(
        self,
        communication_id: UUID,
    ) -> CommunicationLog:
        communication = self.repository.get_by_id(
            communication_id,
        )

        if communication is None:
            raise not_found("Communication log")

        return communication

    def update_delivery_status(
        self,
        *,
        communication_id: UUID,
        status: CommunicationStatus,
        error_message: str | None = None,
    ) -> CommunicationLog:
        communication = self.repository.get_by_id(
            communication_id,
        )

        if communication is None:
            raise not_found("Communication log")

        communication.status = status

        if status in {
            CommunicationStatus.SENT,
            CommunicationStatus.DELIVERED,
        }:
            if communication.sent_at is None:
                communication.sent_at = utc_now()

            communication.error_message = None

        elif status == CommunicationStatus.FAILED:
            communication.error_message = (
                error_message.strip()
                if error_message
                else "Communication delivery failed."
            )

        self.db.commit()
        self.db.refresh(communication)

        return communication

    def _create_pending_log(
        self,
        *,
        recipient: str,
        channel: CommunicationChannel,
        template_id: UUID | None,
    ) -> CommunicationLog:
        communication = CommunicationLog(
            recipient=recipient,
            channel=channel,
            template_id=template_id,
            status=CommunicationStatus.PENDING,
        )

        self.db.add(communication)

        # Persist the history before the external provider is called.
        self.db.commit()
        self.db.refresh(communication)

        return communication

    def _send(
        self,
        *,
        log: CommunicationLog,
        sender: Callable[[], object],
    ) -> CommunicationLog:
        try:
            result = sender()
        except Exception as exc:
            self.db.rollback()

            return self._mark_failed(
                log,
                str(exc) or "Communication provider failed.",
            )

        status = getattr(
            result,
            "status",
            CommunicationStatus.SENT,
        )

        sent_at = getattr(
            result,
            "sent_at",
            None,
        )

        return self._mark_success(
            log,
            status=status,
            sent_at=sent_at,
        )

    def _mark_success(
        self,
        communication: CommunicationLog,
        *,
        status: CommunicationStatus,
        sent_at: datetime | None,
    ) -> CommunicationLog:
        communication.status = status
        communication.sent_at = sent_at or utc_now()
        communication.error_message = None

        self.db.commit()
        self.db.refresh(communication)

        return communication

    def _mark_failed(
        self,
        communication: CommunicationLog,
        error_message: str,
    ) -> CommunicationLog:
        communication.status = CommunicationStatus.FAILED
        communication.error_message = (
            error_message.strip() or "Communication provider failed."
        )

        self.db.commit()
        self.db.refresh(communication)

        return communication
