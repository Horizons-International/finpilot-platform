"""Native-async support ticket workflow with explicit support-agent scoping."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support_ticket import (
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketComment,
    SupportTicketHistory,
)
from app.models.user import User
from app.schemas.support_ticket import SupportTicketCommentCreate, SupportTicketCreate
from app.utils.enums import SupportTicketStatus, UserRole, UserStatus
from app.utils.errors import bad_request, conflict, forbidden, not_found

_STAFF_ROLES = {
    UserRole.SUPPORT_AGENT.value,
    UserRole.ADMINISTRATOR.value,
    UserRole.ORGANIZATION_ADMIN.value,
    UserRole.CUSTOMER_SUCCESS_MANAGER.value,
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

SupportTicketChild = TypeVar(
    "SupportTicketChild",
    SupportTicketComment,
    SupportTicketHistory,
    SupportTicketAttachment,
)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value))


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AsyncSupportTicketService:
    def __init__(self, db: AsyncSession, current_user: dict[str, Any]) -> None:
        self.db = db
        self.actor_id = UUID(str(current_user["sub"]))
        self.tenant_id = UUID(str(current_user["tenant_id"]))
        self.role = str(current_user.get("role", ""))
        self.is_support_agent = self.role == UserRole.SUPPORT_AGENT.value
        self.is_staff = self.role in _STAFF_ROLES
        self.db.info["tenant_id"] = self.tenant_id

    async def get_actor(self) -> User:
        actor = await self.db.scalar(
            select(User).where(
                User.id == self.actor_id,
                User.tenant_id == self.tenant_id,
                User.is_deleted.is_(False),
                User.status == UserStatus.ACTIVE,
            )
        )
        if actor is None:
            raise not_found("User")
        return actor

    def _cross_tenant(self, statement):
        return statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=_CROSS_TENANT_REASON,
        )

    async def _ticket(self, ticket_id: UUID, *, lock: bool = False) -> SupportTicket:
        statement = select(SupportTicket).where(SupportTicket.id == ticket_id)
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
        else:
            statement = statement.where(SupportTicket.tenant_id == self.tenant_id)
            if not self.is_staff:
                statement = statement.where(
                    or_(
                        SupportTicket.created_by == self.actor_id,
                        SupportTicket.assigned_to == self.actor_id,
                    )
                )
        if lock:
            statement = statement.with_for_update()
        ticket = await self.db.scalar(statement)
        if ticket is None:
            raise not_found("Support ticket")
        return ticket

    def _require_staff(self) -> None:
        if not self.is_staff:
            raise forbidden("Only support staff can assign tickets or change status.")

    async def _history(
        self,
        ticket: SupportTicket,
        event_type: str,
        *,
        previous_value: str | None = None,
        new_value: str | None = None,
        details: str | None = None,
    ) -> None:
        self.db.add(
            SupportTicketHistory(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                actor_id=self.actor_id,
                event_type=event_type,
                previous_value=previous_value,
                new_value=new_value,
                details=details,
            )
        )

    async def _commit(
        self, ticket: SupportTicket, refresh: object | None = None
    ) -> None:
        previous = self.db.info.get("tenant_id")
        self.db.info["tenant_id"] = ticket.tenant_id
        try:
            await self.db.commit()
            if refresh is not None:
                await self.db.refresh(refresh)
        except Exception:
            await self.db.rollback()
            raise
        finally:
            if previous is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous

    async def create_ticket(self, payload: SupportTicketCreate) -> SupportTicket:
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
        await self.db.flush()
        await self._history(ticket, "TICKET_CREATED", new_value=ticket.status)
        await self._commit(ticket, ticket)
        return ticket

    async def list_tickets(
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
        statement = select(SupportTicket)
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
            if tenant_id is not None:
                statement = statement.where(SupportTicket.tenant_id == tenant_id)
        else:
            statement = statement.where(SupportTicket.tenant_id == self.tenant_id)
            if not self.is_staff:
                statement = statement.where(
                    or_(
                        SupportTicket.created_by == self.actor_id,
                        SupportTicket.assigned_to == self.actor_id,
                    )
                )
        if status_value is not None:
            statement = statement.where(SupportTicket.status == status_value)
        if category is not None:
            statement = statement.where(SupportTicket.category == category)
        if priority is not None:
            statement = statement.where(SupportTicket.priority == priority)
        if assigned_to is not None:
            statement = statement.where(SupportTicket.assigned_to == assigned_to)
        rows = await self.db.scalars(
            statement.order_by(SupportTicket.created_at.desc())
        )
        return list(rows.all())

    async def get_ticket(self, ticket_id: UUID) -> SupportTicket:
        return await self._ticket(ticket_id)

    async def assign_ticket(
        self, ticket_id: UUID, assignee_id: UUID | None
    ) -> SupportTicket:
        self._require_staff()
        ticket = await self._ticket(ticket_id, lock=True)
        previous_assignee = str(ticket.assigned_to) if ticket.assigned_to else None
        if assignee_id is not None:
            statement = select(User).where(
                User.id == assignee_id,
                User.is_deleted.is_(False),
                User.status == UserStatus.ACTIVE,
            )
            if self.is_support_agent:
                statement = self._cross_tenant(statement)
            else:
                statement = statement.where(User.tenant_id == ticket.tenant_id)
            assignee = await self.db.scalar(statement)
            if assignee is None:
                raise bad_request("Assignee must be an active user.")
            if self.is_support_agent:
                if (
                    assignee.tenant_id != self.tenant_id
                    or _enum(assignee.role) != UserRole.SUPPORT_AGENT.value
                ):
                    raise bad_request(
                        "A platform support ticket must be assigned to an active "
                        "Support Agent in the support team's tenant."
                    )
            elif _enum(assignee.role) not in {
                UserRole.ADMINISTRATOR.value,
                UserRole.ORGANIZATION_ADMIN.value,
                UserRole.CUSTOMER_SUCCESS_MANAGER.value,
            }:
                raise bad_request(
                    "Assignee must be an administrator, organization administrator, "
                    "or Customer Success Manager in the ticket tenant."
                )
        ticket.assigned_to = assignee_id
        await self._history(
            ticket,
            "TICKET_ASSIGNED",
            previous_value=previous_assignee,
            new_value=str(assignee_id) if assignee_id else None,
        )
        if assignee_id is not None and ticket.status == SupportTicketStatus.OPEN.value:
            old = ticket.status
            ticket.status = SupportTicketStatus.ASSIGNED.value
            await self._history(
                ticket, "STATUS_CHANGED", previous_value=old, new_value=ticket.status
            )
        elif (
            assignee_id is None and ticket.status == SupportTicketStatus.ASSIGNED.value
        ):
            old = ticket.status
            ticket.status = SupportTicketStatus.OPEN.value
            await self._history(
                ticket, "STATUS_CHANGED", previous_value=old, new_value=ticket.status
            )
        ticket.updated_at = _now()
        await self._commit(ticket, ticket)
        return ticket

    async def update_status(self, ticket_id: UUID, new_status: str) -> SupportTicket:
        self._require_staff()
        ticket = await self._ticket(ticket_id, lock=True)
        old_status = ticket.status
        if old_status == new_status:
            raise conflict("Ticket already has the requested status.")
        if new_status not in _ALLOWED_TRANSITIONS.get(old_status, set()):
            raise bad_request(
                f"Ticket status cannot change from {old_status} to {new_status}."
            )
        now = _now()
        ticket.status = new_status
        ticket.updated_at = now
        if new_status == SupportTicketStatus.RESOLVED.value:
            ticket.resolved_at, ticket.closed_at = now, None
        elif new_status == SupportTicketStatus.CLOSED.value:
            ticket.resolved_at = ticket.resolved_at or now
            ticket.closed_at = now
        else:
            ticket.resolved_at, ticket.closed_at = None, None
        await self._history(
            ticket, "STATUS_CHANGED", previous_value=old_status, new_value=new_status
        )
        await self._commit(ticket, ticket)
        return ticket

    async def add_comment(
        self, ticket_id: UUID, payload: SupportTicketCommentCreate
    ) -> SupportTicketComment:
        ticket = await self._ticket(ticket_id)
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
        await self._history(
            ticket,
            "COMMENT_ADDED",
            new_value="INTERNAL" if payload.is_internal else "PUBLIC",
        )
        await self._commit(ticket, comment)
        return comment

    async def _children(
        self,
        model,
        ticket_id: UUID,
        *,
        ascending: bool = True,
        include_internal: bool = True,
    ) -> list[SupportTicketChild]:
        ticket = await self._ticket(ticket_id)
        statement = select(model).where(
            model.ticket_id == ticket.id,
            model.tenant_id == ticket.tenant_id,
        )
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
        if model is SupportTicketComment and not include_internal:
            statement = statement.where(SupportTicketComment.is_internal.is_(False))
        order = model.created_at.asc() if ascending else model.created_at.desc()
        rows = await self.db.scalars(statement.order_by(order))
        return list(rows.all())

    async def list_comments(self, ticket_id: UUID) -> list[SupportTicketComment]:
        return await self._children(
            SupportTicketComment, ticket_id, include_internal=self.is_staff
        )

    async def list_history(self, ticket_id: UUID) -> list[SupportTicketHistory]:
        return await self._children(SupportTicketHistory, ticket_id)

    async def list_attachments(self, ticket_id: UUID) -> list[SupportTicketAttachment]:
        return await self._children(SupportTicketAttachment, ticket_id)

    async def get_attachment(
        self, ticket_id: UUID, attachment_id: UUID
    ) -> SupportTicketAttachment:
        ticket = await self._ticket(ticket_id)
        statement = select(SupportTicketAttachment).where(
            SupportTicketAttachment.id == attachment_id,
            SupportTicketAttachment.ticket_id == ticket_id,
            SupportTicketAttachment.tenant_id == ticket.tenant_id,
        )
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
        attachment = await self.db.scalar(statement)
        if attachment is None:
            raise not_found("Support ticket attachment")
        return attachment
