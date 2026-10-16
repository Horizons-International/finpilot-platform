"""Tenant-aware webhook subscription management."""

import secrets
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.webhook import Webhook, WebhookEvent
from app.repositories.webhook_repository import WebhookRepository
from app.schemas.webhook import WebhookCreate, WebhookUpdate
from app.services.audit_service import AuditService
from app.services.tenant_access_audit import deny_tenant_access
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, WebhookDeliveryStatus, WebhookStatus
from app.webhooks.security import encrypt_secret


class WebhookService:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("The database session is bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = WebhookRepository(db, tenant_id=tenant_id)
        self.audit_service = AuditService(db)

    def _get(self, webhook_id: UUID, *, lock: bool = False) -> Webhook:
        webhook = self.repository.get_webhook(webhook_id, for_update=lock)
        if webhook is None:
            deny_tenant_access(
                self.db,
                resource_type="webhook",
                resource_id=webhook_id,
                resource_name="Webhook",
            )
        return webhook

    def create(
        self,
        *,
        data: WebhookCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[Webhook, str]:
        signing_secret = "whsec_" + secrets.token_urlsafe(36)
        webhook = Webhook(
            tenant_id=self.tenant_id,
            endpoint_url=data.endpoint_url,
            secret_key=encrypt_secret(signing_secret),
            event_types=data.event_types,
            status=WebhookStatus.ACTIVE,
        )
        self.repository.create(webhook)
        self.audit_service.log_event(
            event_type=AuditEventType.WEBHOOK_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="webhook",
            resource_id=webhook.id,
        )
        self.db.commit()
        self.db.refresh(webhook)
        return webhook, signing_secret

    def list_all(self, *, status: WebhookStatus | None = None) -> list[Webhook]:
        return self.repository.list_webhooks(status=status)

    def get_by_id(self, webhook_id: UUID) -> Webhook:
        return self._get(webhook_id)

    def update(
        self,
        *,
        webhook_id: UUID,
        data: WebhookUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Webhook:
        webhook = self._get(webhook_id, lock=True)
        values = {
            key: value
            for key, value in data.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if not values:
            from app.utils.errors import bad_request

            raise bad_request("At least one webhook field must be provided.")
        for field, value in values.items():
            setattr(webhook, field, value)
        webhook.updated_at = utc_now()
        self.audit_service.log_event(
            event_type=AuditEventType.WEBHOOK_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="webhook",
            resource_id=webhook.id,
        )
        self.db.commit()
        self.db.refresh(webhook)
        return webhook

    def set_status(
        self,
        *,
        webhook_id: UUID,
        status: WebhookStatus,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Webhook:
        webhook = self._get(webhook_id, lock=True)
        if webhook.status == status:
            from app.utils.errors import bad_request

            raise bad_request("Webhook already has the requested status.")
        webhook.status = status
        webhook.updated_at = utc_now()
        self.audit_service.log_event(
            event_type=(
                AuditEventType.WEBHOOK_ENABLED
                if status == WebhookStatus.ACTIVE
                else AuditEventType.WEBHOOK_DISABLED
            ),
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="webhook",
            resource_id=webhook.id,
        )
        self.db.commit()
        self.db.refresh(webhook)
        return webhook

    def list_deliveries(
        self,
        webhook_id: UUID,
        *,
        status: WebhookDeliveryStatus | None = None,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        self._get(webhook_id)
        return self.repository.list_events(
            webhook_id,
            status=status,
            limit=limit,
        )
