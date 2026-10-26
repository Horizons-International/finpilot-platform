"""Business rules for secure customer support ticket workflows."""

from datetime import datetime, timezone
from pathlib import PurePath
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.models.support_ticket import (
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketComment,
    SupportTicketHistory,
)
from app.models.user import User
from app.repositories.support_ticket_repository import SupportTicketRepository
from app.schemas.support_ticket import (
    SupportTicketCommentCreate,
    SupportTicketCreate,
)
from app.storages.base_storage import BaseStorage
from app.utils.enums import SupportTicketStatus, UserRole, UserStatus
from app.utils.errors import bad_request, conflict, forbidden, not_found

_SUPPORT_STAFF_ROLES = {
    UserRole.SUPPORT_AGENT,
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.CUSTOMER_SUCCESS_MANAGER,
}
_CROSS_TENANT_REASON = (
    "authorized Support Agent manages customer support tickets across tenants"
)
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"ASSIGNED", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"},
    "ASSIGNED": {"OPEN", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"},
    "IN_PROGRESS": {"OPEN", "ASSIGNED", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"},
    "WAITING_CUSTOMER": {"OPEN", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"},
    "RESOLVED": {"OPEN", "ASSIGNED", "IN_PROGRESS", "CLOSED"},
    "CLOSED": {"OPEN"},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


class SupportTicketService:
    """Enforce ownership, support-agent access, workflow and attachment rules."""

    def __init__(
        self,
        db: Session,
        actor: User,
        storage: BaseStorage | None = None,
    ) -> None:
        self.db = db
        self.actor = actor
        self.tenant_id = actor.tenant_id
        self.actor_id = actor.id
        self.storage = storage
        self.is_support_agent = _enum_value(actor.role) == UserRole.SUPPORT_AGENT.value
        self.is_staff = _enum_value(actor.role) in {
            role.value for role in _SUPPORT_STAFF_ROLES
        }
        existing_tenant = db.info.get("tenant_id")
        if existing_tenant is not None and existing_tenant != self.tenant_id:
            raise ValueError("The database session is already bound to another tenant.")
        db.info["tenant_id"] = self.tenant_id
        self.repository = SupportTicketRepository(
            db,
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
            is_support_agent=self.is_support_agent,
            is_staff=self.is_staff,
        )

    def _require_staff(self) -> None:
        if not self.is_staff:
            raise forbidden("Only support staff can assign tickets or change status.")

    def _require_ticket(self, ticket_id: UUID) -> SupportTicket:
        ticket = self.repository.get_ticket(ticket_id)
        if ticket is None:
            raise not_found("Support ticket")
        return ticket

    def _commit_for_ticket(
        self, ticket: SupportTicket, refresh: object | None = None
    ) -> None:
        """Write a ticket and its child records under the ticket's tenant context.

        A Support Agent is explicitly allowed to serve other customer tenants. The
        active ORM tenant context is switched only around this authorized write and
        is restored even when commit/refresh fails.
        """
        previous_tenant = self.db.info.get("tenant_id")
        self.db.info["tenant_id"] = ticket.tenant_id
        try:
            self.db.commit()
            if refresh is not None:
                self.db.refresh(refresh)
        except Exception:
            self.db.rollback()
            raise
        finally:
            if previous_tenant is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous_tenant

    def _history(
        self,
        ticket: SupportTicket,
        event_type: str,
        *,
        previous_value: str | None = None,
        new_value: str | None = None,
        details: str | None = None,
    ) -> SupportTicketHistory:
        event = SupportTicketHistory(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            actor_id=self.actor_id,
            event_type=event_type,
            previous_value=previous_value,
            new_value=new_value,
            details=details,
        )
        self.db.add(event)
        return event

    def create_ticket(self, payload: SupportTicketCreate) -> SupportTicket:
        ticket = SupportTicket(
            tenant_id=self.tenant_id,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            priority=payload.priority,
            status=SupportTicketStatus.OPEN.value,
            created_by=self.actor_id,
        )
        self.db.add(ticket)
        self.db.flush()
        self._history(ticket, "TICKET_CREATED", new_value=ticket.status)
        self._commit_for_ticket(ticket, ticket)
        return ticket

    def list_tickets(
        self,
        *,
        status_value: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        assigned_to: UUID | None = None,
        tenant_id: UUID | None = None,
    ) -> list[SupportTicket]:
        if (
            tenant_id is not None
            and not self.is_support_agent
            and tenant_id != self.tenant_id
        ):
            raise forbidden("You cannot list tickets for another tenant.")
        return self.repository.list_tickets(
            status_value=status_value,
            category=category,
            priority=priority,
            assigned_to=assigned_to,
            tenant_id=tenant_id,
        )

    def get_ticket(self, ticket_id: UUID) -> SupportTicket:
        return self._require_ticket(ticket_id)

    def assign_ticket(self, ticket_id: UUID, assignee_id: UUID | None) -> SupportTicket:
        self._require_staff()
        ticket = self._require_ticket(ticket_id)
        previous_assignee = str(ticket.assigned_to) if ticket.assigned_to else None
        if assignee_id is not None:
            assignee = self.repository.user_by_id(
                assignee_id, cross_tenant=self.is_support_agent
            )
            if (
                assignee is None
                or assignee.is_deleted
                or _enum_value(assignee.status) != UserStatus.ACTIVE.value
            ):
                raise bad_request("Assignee must be an active user.")
            if self.is_support_agent:
                if (
                    assignee.tenant_id != self.tenant_id
                    or _enum_value(assignee.role) != UserRole.SUPPORT_AGENT.value
                ):
                    raise bad_request(
                        "A platform support ticket must be assigned to an active "
                        "Support Agent in the support team's tenant."
                    )
            else:
                allowed_tenant_roles = {
                    UserRole.ADMINISTRATOR.value,
                    UserRole.ORGANIZATION_ADMIN.value,
                    UserRole.CUSTOMER_SUCCESS_MANAGER.value,
                }
                if assignee.tenant_id != ticket.tenant_id:
                    raise bad_request("Assignee must belong to the ticket's tenant.")
                if _enum_value(assignee.role) not in allowed_tenant_roles:
                    raise bad_request(
                        "Assignee must be an administrator, organization "
                        "administrator, or Customer Success Manager in the "
                        "ticket tenant."
                    )
        ticket.assigned_to = assignee_id
        self._history(
            ticket,
            "TICKET_ASSIGNED",
            previous_value=previous_assignee,
            new_value=str(assignee_id) if assignee_id else None,
        )
        if assignee_id is not None and ticket.status == SupportTicketStatus.OPEN.value:
            old_status = ticket.status
            ticket.status = SupportTicketStatus.ASSIGNED.value
            self._history(
                ticket,
                "STATUS_CHANGED",
                previous_value=old_status,
                new_value=ticket.status,
            )
        elif (
            assignee_id is None and ticket.status == SupportTicketStatus.ASSIGNED.value
        ):
            old_status = ticket.status
            ticket.status = SupportTicketStatus.OPEN.value
            self._history(
                ticket,
                "STATUS_CHANGED",
                previous_value=old_status,
                new_value=ticket.status,
            )
        ticket.updated_at = _utcnow()
        self._commit_for_ticket(ticket, ticket)
        return ticket

    def update_status(self, ticket_id: UUID, new_status: str) -> SupportTicket:
        self._require_staff()
        ticket = self._require_ticket(ticket_id)
        old_status = ticket.status
        if old_status == new_status:
            raise conflict("Ticket already has the requested status.")
        if new_status not in _ALLOWED_TRANSITIONS.get(old_status, set()):
            raise bad_request(
                f"Ticket status cannot change from {old_status} to {new_status}."
            )
        now = _utcnow()
        ticket.status = new_status
        ticket.updated_at = now
        if new_status == SupportTicketStatus.RESOLVED.value:
            ticket.resolved_at = now
            ticket.closed_at = None
        elif new_status == SupportTicketStatus.CLOSED.value:
            if ticket.resolved_at is None:
                ticket.resolved_at = now
            ticket.closed_at = now
        else:
            # Reopening starts a new current resolution cycle. Earlier status events
            # remain in the append-only history for auditability.
            ticket.resolved_at = None
            ticket.closed_at = None
        self._history(
            ticket,
            "STATUS_CHANGED",
            previous_value=old_status,
            new_value=new_status,
        )
        self._commit_for_ticket(ticket, ticket)
        return ticket

    def add_comment(
        self, ticket_id: UUID, payload: SupportTicketCommentCreate
    ) -> SupportTicketComment:
        ticket = self._require_ticket(ticket_id)
        if payload.is_internal and not self.is_staff:
            raise forbidden("Only support staff can add internal notes.")
        comment = SupportTicketComment(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            author_id=self.actor_id,
            body=payload.body,
            is_internal=payload.is_internal,
        )
        self.db.add(comment)
        self._history(
            ticket,
            "COMMENT_ADDED",
            new_value="INTERNAL" if payload.is_internal else "PUBLIC",
        )
        self._commit_for_ticket(ticket, comment)
        return comment

    def list_comments(self, ticket_id: UUID) -> list[SupportTicketComment]:
        self._require_ticket(ticket_id)
        return self.repository.list_comments(ticket_id, include_internal=self.is_staff)

    def list_history(self, ticket_id: UUID) -> list[SupportTicketHistory]:
        self._require_ticket(ticket_id)
        return self.repository.list_history(ticket_id)

    def list_attachments(self, ticket_id: UUID) -> list[SupportTicketAttachment]:
        self._require_ticket(ticket_id)
        return self.repository.list_attachments(ticket_id)

    async def add_attachment(
        self, ticket_id: UUID, upload: UploadFile
    ) -> SupportTicketAttachment:
        if self.storage is None:
            raise RuntimeError("File storage is not configured for support tickets.")
        ticket = self._require_ticket(ticket_id)
        raw_name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        filename = PurePath(raw_name).name[:255]
        content_type = (upload.content_type or "").strip().lower()
        if not filename or filename in {".", ".."}:
            raise bad_request("A valid attachment filename is required.")
        allowed_types: set[str] = set(settings.ALLOWED_FILE_TYPES)
        if content_type not in allowed_types:
            raise bad_request("Attachment content type is not allowed.")
        max_file_size: int = settings.MAX_FILE_SIZE
        if max_file_size <= 0:
            raise bad_request(
                "Attachment upload is not enabled by server configuration."
            )
        content = await upload.read(max_file_size + 1)
        if not content:
            raise bad_request("Empty attachments are not allowed.")
        if len(content) > max_file_size:
            raise bad_request("Attachment exceeds the configured maximum file size.")
        storage_path: str | None = None
        try:
            storage_path = self.storage.save(
                file_content=content,
                filename=filename,
                folder=f"support-tickets/{ticket.tenant_id}/{ticket.id}",
            )
            attachment = SupportTicketAttachment(
                id=uuid4(),
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                original_filename=filename,
                storage_path=storage_path,
                content_type=content_type,
                file_size=len(content),
                uploaded_by=self.actor_id,
            )
            self.db.add(attachment)
            self._history(
                ticket,
                "ATTACHMENT_ADDED",
                new_value=str(attachment.id),
                details=filename,
            )
            self._commit_for_ticket(ticket, attachment)
            return attachment
        except Exception:
            self.db.rollback()
            if storage_path is not None:
                try:
                    if self.storage.exists(storage_path):
                        self.storage.delete(storage_path)
                except Exception:
                    # Preserve the database/storage exception; cleanup is best-effort.
                    pass
            raise

    def download_attachment(
        self, ticket_id: UUID, attachment_id: UUID
    ) -> tuple[bytes, str, str]:
        if self.storage is None:
            raise RuntimeError("File storage is not configured for support tickets.")
        self._require_ticket(ticket_id)
        attachment = self.repository.get_attachment(ticket_id, attachment_id)
        if attachment is None:
            raise not_found("Support ticket attachment")
        if not self.storage.exists(attachment.storage_path):
            raise not_found("Stored support ticket attachment")
        return (
            self.storage.read(attachment.storage_path),
            attachment.original_filename,
            attachment.content_type,
        )
