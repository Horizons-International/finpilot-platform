"""Tenant-scoped persistence for webhook subscriptions and delivery events."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook import Webhook, WebhookEvent
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import WebhookDeliveryStatus, WebhookStatus


class WebhookRepository(TenantScopedRepository[Webhook]):
    """Persist and query webhook configuration and delivery history."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=Webhook, tenant_id=tenant_id)

    def get_webhook(
        self,
        webhook_id: UUID,
        *,
        for_update: bool = False,
    ) -> Webhook | None:
        query = self.query().filter(Webhook.id == webhook_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def list_webhooks(
        self,
        *,
        status: WebhookStatus | None = None,
    ) -> list[Webhook]:
        query = self.query()
        if status is not None:
            query = query.filter(Webhook.status == status)
        return query.order_by(Webhook.created_at.desc()).all()

    def list_events(
        self,
        webhook_id: UUID,
        *,
        status: WebhookDeliveryStatus | None = None,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        statement = select(WebhookEvent).where(
            WebhookEvent.tenant_id == self.tenant_id,
            WebhookEvent.webhook_id == webhook_id,
        )
        if status is not None:
            statement = statement.where(WebhookEvent.status == status)
        statement = statement.order_by(WebhookEvent.created_at.desc()).limit(limit)
        return list(self.db.scalars(statement).all())
