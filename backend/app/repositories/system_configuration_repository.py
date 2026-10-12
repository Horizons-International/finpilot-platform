from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.system_configuration import SystemConfiguration
from app.models.user import User
from app.utils.enums import (
    SystemConfigurationCategory,
    SystemConfigurationStatus,
)


class SystemConfigurationRepository:
    """Tenant-scoped system configuration and its audit history."""

    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for system configurations.")
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != resolved_tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant."
            )
        # Also scope relationship/lazy loads covered by tenant_filter.py.
        db.info["tenant_id"] = resolved_tenant_id
        self.db = db
        self.tenant_id = resolved_tenant_id

    def _validate_updater(self, updated_by: UUID | None) -> None:
        if updated_by is None:
            return
        user_id = self.db.scalar(
            select(User.id).where(
                User.id == updated_by,
                User.tenant_id == self.tenant_id,
            )
        )
        if user_id is None:
            raise ValueError(
                "Configuration updater does not belong to the current tenant."
            )

    def _assert_owned(self, configuration: SystemConfiguration) -> None:
        if configuration.tenant_id != self.tenant_id:
            raise ValueError("Cannot modify a configuration owned by another tenant.")
        exists = self.db.scalar(
            select(SystemConfiguration.id).where(
                SystemConfiguration.id == configuration.id,
                SystemConfiguration.tenant_id == self.tenant_id,
            )
        )
        if exists is None:
            raise ValueError("Configuration does not belong to the current tenant.")

    def create(self, configuration: SystemConfiguration) -> SystemConfiguration:
        if (
            configuration.tenant_id is not None
            and configuration.tenant_id != self.tenant_id
        ):
            raise ValueError("Cannot create a configuration for another tenant.")
        self._validate_updater(configuration.updated_by)
        configuration.tenant_id = self.tenant_id
        self.db.add(configuration)
        self.db.flush()
        self.db.refresh(configuration)
        return configuration

    def get_by_id(
        self,
        configuration_id: UUID,
        *,
        for_update: bool = False,
    ) -> SystemConfiguration | None:
        statement = select(SystemConfiguration).where(
            SystemConfiguration.tenant_id == self.tenant_id,
            SystemConfiguration.id == configuration_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_by_key(self, key: str) -> SystemConfiguration | None:
        return self.db.scalar(
            select(SystemConfiguration).where(
                SystemConfiguration.tenant_id == self.tenant_id,
                SystemConfiguration.key == key,
            )
        )

    def list_all(
        self,
        *,
        category: SystemConfigurationCategory | None = None,
        status: SystemConfigurationStatus | None = None,
    ) -> list[SystemConfiguration]:
        filters = [SystemConfiguration.tenant_id == self.tenant_id]
        if category is not None:
            filters.append(SystemConfiguration.category == category)
        if status is not None:
            filters.append(SystemConfiguration.status == status)
        statement = (
            select(SystemConfiguration)
            .where(*filters)
            .order_by(
                SystemConfiguration.key.asc(),
            )
        )
        return list(self.db.scalars(statement).all())

    def get_audit_history(self, configuration_id: UUID) -> list[AuditLog]:
        # Both the audit tenant and resource id are required. Filtering only by
        # resource_id is insufficient if identifiers or requests are forged.
        statement = (
            select(AuditLog)
            .where(
                AuditLog.tenant_id == self.tenant_id,
                AuditLog.resource_type == "system_configuration",
                AuditLog.resource_id == configuration_id,
            )
            .order_by(AuditLog.timestamp.desc())
        )
        return list(self.db.scalars(statement).all())

    def update(self, configuration: SystemConfiguration) -> SystemConfiguration:
        self._assert_owned(configuration)
        self._validate_updater(configuration.updated_by)
        self.db.flush()
        self.db.refresh(configuration)
        return configuration
