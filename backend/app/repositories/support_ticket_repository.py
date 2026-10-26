"""Persistence queries for tenant-scoped support tickets."""

from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models.support_ticket import (
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketComment,
    SupportTicketHistory,
)
from app.models.user import User

_CROSS_TENANT_REASON = (
    "authorized Support Agent manages customer support tickets across tenants"
)


class SupportTicketRepository:
    def __init__(
        self,
        db: Session,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        is_support_agent: bool,
        is_staff: bool,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.is_support_agent = is_support_agent
        self.is_staff = is_staff

    def _cross_tenant(self, statement: Select) -> Select:
        return statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=_CROSS_TENANT_REASON,
        )

    def get_ticket(self, ticket_id: UUID) -> SupportTicket | None:
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
        return self.db.scalar(statement)

    def list_tickets(
        self,
        *,
        status_value: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        assigned_to: UUID | None = None,
        tenant_id: UUID | None = None,
    ) -> list[SupportTicket]:
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
        statement = statement.order_by(SupportTicket.created_at.desc())
        return list(self.db.scalars(statement).all())

    def list_comments(
        self, ticket_id: UUID, *, include_internal: bool
    ) -> list[SupportTicketComment]:
        statement = select(SupportTicketComment).where(
            SupportTicketComment.ticket_id == ticket_id
        )
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
        else:
            statement = statement.where(
                SupportTicketComment.tenant_id == self.tenant_id
            )
        if not include_internal:
            statement = statement.where(SupportTicketComment.is_internal.is_(False))
        statement = statement.order_by(SupportTicketComment.created_at.asc())
        return list(self.db.scalars(statement).all())

    def list_attachments(self, ticket_id: UUID) -> list[SupportTicketAttachment]:
        statement = select(SupportTicketAttachment).where(
            SupportTicketAttachment.ticket_id == ticket_id
        )
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
        else:
            statement = statement.where(
                SupportTicketAttachment.tenant_id == self.tenant_id
            )
        statement = statement.order_by(SupportTicketAttachment.created_at.asc())
        return list(self.db.scalars(statement).all())

    def get_attachment(
        self, ticket_id: UUID, attachment_id: UUID
    ) -> SupportTicketAttachment | None:
        statement = select(SupportTicketAttachment).where(
            SupportTicketAttachment.ticket_id == ticket_id,
            SupportTicketAttachment.id == attachment_id,
        )
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
        else:
            statement = statement.where(
                SupportTicketAttachment.tenant_id == self.tenant_id
            )
        return self.db.scalar(statement)

    def list_history(self, ticket_id: UUID) -> list[SupportTicketHistory]:
        statement = select(SupportTicketHistory).where(
            SupportTicketHistory.ticket_id == ticket_id
        )
        if self.is_support_agent:
            statement = self._cross_tenant(statement)
        else:
            statement = statement.where(
                SupportTicketHistory.tenant_id == self.tenant_id
            )
        statement = statement.order_by(SupportTicketHistory.created_at.asc())
        return list(self.db.scalars(statement).all())

    def user_by_id(self, user_id: UUID, *, cross_tenant: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if cross_tenant:
            statement = self._cross_tenant(statement)
        else:
            statement = statement.where(User.tenant_id == self.tenant_id)
        return self.db.scalar(statement)
