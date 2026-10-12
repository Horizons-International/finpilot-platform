from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.communication.providers.base import EmailProvider, SMSProvider
from app.communication.schemas import EmailMessage, SMSMessage
from app.models.communication_log import CommunicationLog
from app.repositories.communication_log_repository import CommunicationLogRepository
from app.services.tenant_context import resolve_tenant_context
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
        tenant_id: UUID | None = None,
    ) -> None:
        self.db = db
        self._requested_tenant_id = tenant_id
        self.tenant_id: UUID | None = tenant_id
        self.repository: CommunicationLogRepository | None = None
        self.email_provider = email_provider
        self.sms_provider = sms_provider

    def _repository(self) -> CommunicationLogRepository:
        if self.repository is None:
            self.tenant_id = resolve_tenant_context(
                self.db, self._requested_tenant_id, resource_name="communication logs"
            )
            self.repository = CommunicationLogRepository(
                self.db, tenant_id=self.tenant_id
            )
        return self.repository

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
            raise bad_request("Email subject is required.")
        if not normalized_body:
            raise bad_request("Email body is required.")
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
            raise bad_request("SMS message is required.")
        log = self._create_pending_log(
            recipient=normalized_recipient,
            channel=CommunicationChannel.SMS,
            template_id=template_id,
        )
        return self._send(
            log=log,
            sender=lambda: self.sms_provider.send(
                SMSMessage(recipient=normalized_recipient, body=normalized_body)
            ),
        )

    def get_communication(self, communication_id: UUID) -> CommunicationLog:
        communication = self._repository().get_by_id(communication_id)
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
        communication = self._repository().get_by_id(communication_id)
        if communication is None:
            raise not_found("Communication log")
        communication.status = status
        if status in {CommunicationStatus.SENT, CommunicationStatus.DELIVERED}:
            if communication.sent_at is None:
                communication.sent_at = utc_now()
            communication.error_message = None
        elif status == CommunicationStatus.FAILED:
            communication.error_message = (
                error_message.strip()
                if error_message
                else "Communication delivery failed."
            )
        communication = self._repository().update(communication)
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
        tenant_id = resolve_tenant_context(
            self.db, self._requested_tenant_id, resource_name="communication logs"
        )
        self.tenant_id = tenant_id
        communication = CommunicationLog(
            tenant_id=tenant_id,
            recipient=recipient,
            channel=channel,
            template_id=template_id,
            status=CommunicationStatus.PENDING,
        )
        communication = self._repository().create(communication)
        # Persist the history before invoking the external provider.
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
            # Re-load under the tenant scope after rollback; don't mutate a
            # possibly detached or stale cross-transaction object.
            current = self._repository().get_by_id(log.id)
            if current is None:
                raise not_found("Communication log") from exc
            return self._mark_failed(
                current, str(exc) or "Communication provider failed."
            )
        status = getattr(result, "status", CommunicationStatus.SENT)
        sent_at = getattr(result, "sent_at", None)
        current = self._repository().get_by_id(log.id)
        if current is None:
            raise not_found("Communication log")
        return self._mark_success(current, status=status, sent_at=sent_at)

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
        self._repository().update(communication)
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
        self._repository().update(communication)
        self.db.commit()
        self.db.refresh(communication)
        return communication
