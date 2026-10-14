"""Tenant-aware lifecycle and health monitoring for external integrations."""

import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.adapters.base import IntegrationAdapter
from app.integrations.adapters.registry import adapter_registry
from app.models.integration import Integration
from app.repositories.integration_repository import IntegrationRepository
from app.schemas.integration import IntegrationCreate, IntegrationUpdate
from app.services.audit_service import AuditService
from app.services.tenant_access_audit import deny_tenant_access
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, IntegrationStatus, IntegrationType
from app.utils.errors import bad_request

logger = logging.getLogger(__name__)

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
    r"password|secret|authorization)\s*([:=])\s*[^\s,;]+"
)


def _safe_message(message: str) -> str:
    """Redact common credential assignments before persisting provider messages."""
    redacted = _SECRET_ASSIGNMENT_RE.sub(r"\1\2[REDACTED]", message)
    return redacted[:1000]


class IntegrationService:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repository = IntegrationRepository(db, tenant_id)
        self.audit_service = AuditService(db)

    def _adapter(
        self,
        provider_name: str,
        integration_type: IntegrationType,
        configuration: dict[str, Any],
    ) -> IntegrationAdapter:
        try:
            adapter = adapter_registry.create(
                provider_name,
                integration_type,
                configuration,
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

    def _audit(
        self,
        *,
        event_type: AuditEventType,
        integration: Integration,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.audit_service.log_event(
            event_type=event_type,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="integration",
            resource_id=integration.id,
        )

    def create(
        self,
        *,
        data: IntegrationCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Integration:
        self._adapter(data.provider_name, data.integration_type, data.configuration)
        integration = Integration(
            tenant_id=self.tenant_id,
            provider_name=data.provider_name,
            integration_type=data.integration_type,
            configuration=data.configuration,
            is_enabled=data.is_enabled,
            status=IntegrationStatus.UNKNOWN,
        )
        self.repository.create(integration)
        self._audit(
            event_type=AuditEventType.INTEGRATION_CREATED,
            integration=integration,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def list_all(
        self,
        *,
        integration_type: IntegrationType | None = None,
        status: IntegrationStatus | None = None,
        is_enabled: bool | None = None,
    ) -> list[Integration]:
        return self.repository.list_all(
            integration_type=integration_type,
            status=status,
            is_enabled=is_enabled,
        )

    def get_by_id(self, integration_id: UUID) -> Integration:
        integration = self.repository.get_by_id(integration_id)
        if integration is None:
            deny_tenant_access(
                self.db,
                resource_type="integration",
                resource_id=integration_id,
                resource_name="Integration",
            )
        return integration

    def update_configuration(
        self,
        *,
        integration_id: UUID,
        data: IntegrationUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Integration:
        integration = self.get_by_id(integration_id)
        self._adapter(
            integration.provider_name,
            integration.integration_type,
            data.configuration,
        )
        integration.configuration = data.configuration
        integration.status = IntegrationStatus.UNKNOWN
        integration.last_checked_at = None
        integration.last_error = None
        self._audit(
            event_type=AuditEventType.INTEGRATION_UPDATED,
            integration=integration,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def set_enabled(
        self,
        *,
        integration_id: UUID,
        is_enabled: bool,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Integration:
        integration = self.get_by_id(integration_id)
        if is_enabled:
            self._adapter(
                integration.provider_name,
                integration.integration_type,
                integration.configuration,
            )
        if integration.is_enabled == is_enabled:
            return integration
        integration.is_enabled = is_enabled
        event_type = (
            AuditEventType.INTEGRATION_ENABLED
            if is_enabled
            else AuditEventType.INTEGRATION_DISABLED
        )
        self._audit(
            event_type=event_type,
            integration=integration,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def check_connection(
        self,
        *,
        integration_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[Integration, str]:
        integration = self.get_by_id(integration_id)
        integration.last_checked_at = utc_now()
        try:
            adapter = self._adapter(
                integration.provider_name,
                integration.integration_type,
                integration.configuration,
            )
            result = adapter.check_connection()
            integration.status = result.status
            message = _safe_message(result.message)
            if result.status == IntegrationStatus.HEALTHY:
                integration.last_success_at = integration.last_checked_at
                integration.last_error = None
            elif result.status == IntegrationStatus.ERROR:
                integration.last_error = message
            else:
                integration.last_error = None
        except Exception as exc:
            # Never expose or persist the provider exception text: SDKs sometimes
            # include credential values or full request URLs in their messages.
            logger.warning(
                "Integration connection check failed for integration %s "
                "and tenant %s (%s).",
                integration.id,
                self.tenant_id,
                type(exc).__name__,
            )
            integration.status = IntegrationStatus.ERROR
            integration.last_error = (
                f"Connection check failed ({type(exc).__name__}). "
                "Review sanitized server diagnostics for more detail."
            )
            message = integration.last_error

        event_type = (
            AuditEventType.INTEGRATION_CONNECTION_FAILED
            if integration.status == IntegrationStatus.ERROR
            else AuditEventType.INTEGRATION_CONNECTION_CHECKED
        )
        self._audit(
            event_type=event_type,
            integration=integration,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
        self.db.refresh(integration)
        return integration, message
