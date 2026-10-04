from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.system_configuration import SystemConfiguration
from app.utils.enums import (
    SystemConfigurationCategory,
    SystemConfigurationStatus,
)


class SystemConfigurationRepository:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

    def create(
        self,
        configuration: SystemConfiguration,
    ) -> SystemConfiguration:
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
            SystemConfiguration.id == configuration_id,
        )

        if for_update:
            statement = statement.with_for_update()

        return self.db.scalar(statement)

    def get_by_key(
        self,
        key: str,
    ) -> SystemConfiguration | None:
        return self.db.scalar(
            select(SystemConfiguration).where(
                SystemConfiguration.key == key,
            )
        )

    def list_all(
        self,
        *,
        category: SystemConfigurationCategory | None = None,
        status: SystemConfigurationStatus | None = None,
    ) -> list[SystemConfiguration]:
        filters = []

        if category is not None:
            filters.append(
                SystemConfiguration.category == category,
            )

        if status is not None:
            filters.append(
                SystemConfiguration.status == status,
            )

        statement = select(SystemConfiguration).order_by(
            SystemConfiguration.key.asc(),
        )

        if filters:
            statement = statement.where(*filters)

        return list(
            self.db.scalars(statement).all(),
        )

    def get_audit_history(
        self,
        configuration_id: UUID,
    ) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .where(
                AuditLog.resource_type == "system_configuration",
                AuditLog.resource_id == configuration_id,
            )
            .order_by(
                AuditLog.timestamp.desc(),
            )
        )

        return list(
            self.db.scalars(statement).all(),
        )

    def update(
        self,
        configuration: SystemConfiguration,
    ) -> SystemConfiguration:
        self.db.flush()
        self.db.refresh(configuration)

        return configuration
