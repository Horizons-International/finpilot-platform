"""Native-async tenant services for webhooks, integrations and API keys."""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.integrations.adapters.registry import adapter_registry
from app.models.api_key import APIKey, APIKeyUsage
from app.models.integration import Integration
from app.models.webhook import Webhook, WebhookEvent
from app.schemas.api_key import APIKeyCreate
from app.schemas.integration import IntegrationCreate, IntegrationUpdate
from app.schemas.webhook import WebhookCreate, WebhookUpdate
from app.services.async_audit_service import AsyncAuditService
from app.utils.date_time import utc_now
from app.utils.enums import (
    APIKeyStatus,
    AuditEventType,
    IntegrationStatus,
    IntegrationType,
    WebhookDeliveryStatus,
    WebhookStatus,
)
from app.utils.errors import bad_request, not_found
from app.webhooks.security import encrypt_secret

logger = logging.getLogger(__name__)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"client[_ -]?secret|password|secret|authorization)"
    r"\s*([:=])\s*[^\s,;]+"
)


def _safe_message(message: str) -> str:
    return _SECRET_ASSIGNMENT_RE.sub(r"\1\2[REDACTED]", message)[:1000]


def _bind(db: AsyncSession, tenant_id: UUID) -> None:
    existing = db.info.get("tenant_id")
    if existing is not None and existing != tenant_id:
        raise ValueError("The database session is already bound to another tenant.")
    db.info["tenant_id"] = tenant_id


class AsyncWebhookService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        _bind(db, tenant_id)
        self.db, self.tenant_id = db, tenant_id
        self.audit = AsyncAuditService(db)

    async def _get(self, webhook_id: UUID, *, lock: bool = False) -> Webhook:
        statement = select(Webhook).where(
            Webhook.id == webhook_id, Webhook.tenant_id == self.tenant_id
        )
        if lock:
            statement = statement.with_for_update()
        item = await self.db.scalar(statement)
        if item is None:
            await self.audit.log_access_denied(
                resource_type="webhook",
                resource_id=webhook_id,
                user_id=self.db.info.get("tenant_user_id"),
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("Webhook")
        return item

    async def create(
        self,
        *,
        data: WebhookCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[Webhook, str]:
        secret = "whsec_" + secrets.token_urlsafe(36)
        webhook = Webhook(
            tenant_id=self.tenant_id,
            endpoint_url=data.endpoint_url,
            secret_key=encrypt_secret(secret),
            event_types=data.event_types,
            status=WebhookStatus.ACTIVE,
        )
        self.db.add(webhook)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.WEBHOOK_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="webhook",
            resource_id=webhook.id,
        )
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook, secret

    async def list_all(self, *, status: WebhookStatus | None = None) -> list[Webhook]:
        statement = select(Webhook).where(Webhook.tenant_id == self.tenant_id)
        if status is not None:
            statement = statement.where(Webhook.status == status)
        result = await self.db.scalars(statement.order_by(Webhook.created_at.desc()))
        return list(result.all())

    async def get_by_id(self, webhook_id: UUID) -> Webhook:
        return await self._get(webhook_id)

    async def update(
        self,
        *,
        webhook_id: UUID,
        data: WebhookUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Webhook:
        webhook = await self._get(webhook_id, lock=True)
        values = {
            key: value
            for key, value in data.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if not values:
            raise bad_request("At least one webhook field must be provided.")
        for field, value in values.items():
            setattr(webhook, field, value)
        webhook.updated_at = utc_now()
        await self.audit.log_event(
            event_type=AuditEventType.WEBHOOK_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="webhook",
            resource_id=webhook.id,
        )
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def set_status(
        self,
        *,
        webhook_id: UUID,
        status: WebhookStatus,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Webhook:
        webhook = await self._get(webhook_id, lock=True)
        if webhook.status == status:
            raise bad_request("Webhook already has the requested status.")
        webhook.status = status
        webhook.updated_at = utc_now()
        await self.audit.log_event(
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
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def list_deliveries(
        self,
        webhook_id: UUID,
        *,
        status: WebhookDeliveryStatus | None = None,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        await self._get(webhook_id)
        statement = select(WebhookEvent).where(
            WebhookEvent.tenant_id == self.tenant_id,
            WebhookEvent.webhook_id == webhook_id,
        )
        if status is not None:
            statement = statement.where(WebhookEvent.status == status)
        result = await self.db.scalars(
            statement.order_by(WebhookEvent.created_at.desc()).limit(limit)
        )
        return list(result.all())


class AsyncIntegrationService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        _bind(db, tenant_id)
        self.db, self.tenant_id = db, tenant_id
        self.audit = AsyncAuditService(db)

    @staticmethod
    def _adapter(
        provider_name: str,
        integration_type: IntegrationType,
        configuration: dict[str, Any],
    ):
        try:
            adapter = adapter_registry.create(
                provider_name, integration_type, configuration
            )
        except KeyError as exc:
            raise bad_request(
                f"No adapter is registered for provider '{provider_name}' "
                f"and integration type '{integration_type.value}'."
            ) from exc
        try:
            adapter.validate_configuration()
        except ValueError as exc:
            raise bad_request(str(exc)) from exc
        return adapter

    async def _get(self, integration_id: UUID, *, lock: bool = False) -> Integration:
        statement = select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        integration = await self.db.scalar(statement)
        if integration is None:
            await self.audit.log_access_denied(
                resource_type="integration",
                resource_id=integration_id,
                user_id=self.db.info.get("tenant_user_id"),
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("Integration")
        return integration

    async def _audit(
        self,
        event: AuditEventType,
        item: Integration,
        user_id: UUID,
        email: str,
        ip: str | None,
        agent: str | None,
    ) -> None:
        await self.audit.log_event(
            event_type=event,
            user_id=user_id,
            email=email,
            ip_address=ip,
            user_agent=agent,
            resource_type="integration",
            resource_id=item.id,
        )

    async def create(
        self,
        *,
        data: IntegrationCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Integration:
        self._adapter(data.provider_name, data.integration_type, data.configuration)
        item = Integration(
            tenant_id=self.tenant_id,
            provider_name=data.provider_name,
            integration_type=data.integration_type,
            configuration=data.configuration,
            is_enabled=data.is_enabled,
            status=IntegrationStatus.UNKNOWN,
        )
        self.db.add(item)
        await self.db.flush()
        await self._audit(
            AuditEventType.INTEGRATION_CREATED,
            item,
            user_id,
            email,
            ip_address,
            user_agent,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_all(
        self,
        *,
        integration_type: IntegrationType | None = None,
        status: IntegrationStatus | None = None,
        is_enabled: bool | None = None,
    ) -> list[Integration]:
        statement = select(Integration).where(Integration.tenant_id == self.tenant_id)
        if integration_type is not None:
            statement = statement.where(
                Integration.integration_type == integration_type
            )
        if status is not None:
            statement = statement.where(Integration.status == status)
        if is_enabled is not None:
            statement = statement.where(Integration.is_enabled.is_(is_enabled))
        rows = await self.db.scalars(statement.order_by(Integration.created_at.desc()))
        return list(rows.all())

    async def get_by_id(self, integration_id: UUID) -> Integration:
        return await self._get(integration_id)

    async def update_configuration(
        self,
        *,
        integration_id: UUID,
        data: IntegrationUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Integration:
        item = await self._get(integration_id, lock=True)
        self._adapter(item.provider_name, item.integration_type, data.configuration)
        item.configuration = data.configuration
        item.status = IntegrationStatus.UNKNOWN
        item.last_checked_at = None
        item.last_error = None
        await self._audit(
            AuditEventType.INTEGRATION_UPDATED,
            item,
            user_id,
            email,
            ip_address,
            user_agent,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def set_enabled(
        self,
        *,
        integration_id: UUID,
        is_enabled: bool,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Integration:
        item = await self._get(integration_id, lock=True)
        if is_enabled:
            self._adapter(item.provider_name, item.integration_type, item.configuration)
        if item.is_enabled == is_enabled:
            return item
        item.is_enabled = is_enabled
        await self._audit(
            (
                AuditEventType.INTEGRATION_ENABLED
                if is_enabled
                else AuditEventType.INTEGRATION_DISABLED
            ),
            item,
            user_id,
            email,
            ip_address,
            user_agent,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def check_connection(
        self,
        *,
        integration_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[Integration, str]:
        item = await self._get(integration_id, lock=True)
        item.last_checked_at = utc_now()
        try:
            adapter = self._adapter(
                item.provider_name, item.integration_type, item.configuration
            )
            # Adapter may perform network I/O; never run it in the event loop.
            result = await run_in_threadpool(adapter.check_connection)
            item.status = result.status
            message = _safe_message(result.message)
            if result.status == IntegrationStatus.HEALTHY:
                item.last_success_at = item.last_checked_at
                item.last_error = None
            elif result.status == IntegrationStatus.ERROR:
                item.last_error = message
            else:
                item.last_error = None
        except Exception as exc:
            logger.warning(
                "Integration check failed for %s (%s)", item.id, type(exc).__name__
            )
            item.status = IntegrationStatus.ERROR
            item.last_error = (
                f"Connection check failed ({type(exc).__name__}). "
                "Review sanitized server diagnostics for more detail."
            )
            message = item.last_error
        event = (
            AuditEventType.INTEGRATION_CONNECTION_FAILED
            if item.status == IntegrationStatus.ERROR
            else AuditEventType.INTEGRATION_CONNECTION_CHECKED
        )
        await self._audit(event, item, user_id, email, ip_address, user_agent)
        await self.db.commit()
        await self.db.refresh(item)
        return item, message


class AsyncAPIKeyService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        _bind(db, tenant_id)
        self.db, self.tenant_id = db, tenant_id
        self.audit = AsyncAuditService(db)

    @staticmethod
    def hash_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_secret() -> str:
        return f"fp_live_{secrets.token_urlsafe(32)}"

    async def create(
        self,
        *,
        data: APIKeyCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[APIKey, str]:
        raw = self._generate_secret()
        item = APIKey(
            tenant_id=self.tenant_id,
            name=data.name,
            key_hash=self.hash_key(raw),
            permissions=list(data.permissions),
            status=APIKeyStatus.ACTIVE,
            created_by=user_id,
        )
        self.db.add(item)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.API_KEY_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="api_key",
            resource_id=item.id,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item, raw

    async def list_all(self) -> list[APIKey]:
        rows = await self.db.scalars(
            select(APIKey)
            .where(APIKey.tenant_id == self.tenant_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(rows.all())

    async def _get(self, api_key_id: UUID, *, lock: bool = False) -> APIKey:
        statement = select(APIKey).where(
            APIKey.id == api_key_id, APIKey.tenant_id == self.tenant_id
        )
        if lock:
            statement = statement.with_for_update()
        item = await self.db.scalar(statement)
        if item is None:
            await self.audit.log_access_denied(
                resource_type="api_key",
                resource_id=api_key_id,
                user_id=self.db.info.get("tenant_user_id"),
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("API key")
        return item

    async def revoke(
        self,
        *,
        api_key_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> APIKey:
        item = await self._get(api_key_id, lock=True)
        if item.status != APIKeyStatus.REVOKED:
            item.status = APIKeyStatus.REVOKED
            item.revoked_at = utc_now()
            await self.audit.log_event(
                event_type=AuditEventType.API_KEY_REVOKED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="api_key",
                resource_id=item.id,
            )
            await self.db.commit()
            await self.db.refresh(item)
        return item

    async def list_usage(
        self, api_key_id: UUID, *, limit: int = 100
    ) -> list[APIKeyUsage]:
        await self._get(api_key_id)
        rows = await self.db.scalars(
            select(APIKeyUsage)
            .where(
                APIKeyUsage.api_key_id == api_key_id,
                APIKeyUsage.tenant_id == self.tenant_id,
            )
            .order_by(APIKeyUsage.created_at.desc())
            .limit(limit)
        )
        return list(rows.all())
