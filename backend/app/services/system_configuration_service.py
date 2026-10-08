from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.system_configuration import SystemConfiguration
from app.repositories.system_configuration_repository import (
    SystemConfigurationRepository,
)
from app.schemas.system_configuration import (
    SystemConfigurationCreate,
    SystemConfigurationUpdate,
)
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    SystemConfigurationCategory,
    SystemConfigurationStatus,
)
from app.utils.errors import bad_request, not_found
from app.utils.validators.system_configuration import (
    validate_configuration,
)


class SystemConfigurationService:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repository = SystemConfigurationRepository(
            db,
            tenant_id,
        )
        self.audit_service = AuditService(db)

    def create(
        self,
        *,
        data: SystemConfigurationCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SystemConfiguration:
        key = data.key.strip()

        if self.repository.get_by_key(key) is not None:
            raise bad_request(
                "A system configuration with this key already exists.",
            )

        try:
            validated_value = validate_configuration(
                key=key,
                category=data.category,
                value=data.value,
            )
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        configuration = SystemConfiguration(
            tenant_id=self.tenant_id,
            key=key,
            value=validated_value,
            category=data.category,
            status=data.status,
            updated_by=user_id,
            updated_at=utc_now(),
        )

        self.repository.create(configuration)

        self.audit_service.log_event(
            event_type=AuditEventType.SYSTEM_CONFIGURATION_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="system_configuration",
            resource_id=configuration.id,
        )

        self.db.commit()
        self.db.refresh(configuration)

        return configuration

    def list_all(
        self,
        *,
        category: SystemConfigurationCategory | None = None,
        status: SystemConfigurationStatus | None = None,
    ) -> list[SystemConfiguration]:
        return self.repository.list_all(
            category=category,
            status=status,
        )

    def get_by_id(
        self,
        configuration_id: UUID,
    ) -> SystemConfiguration:
        configuration = self.repository.get_by_id(
            configuration_id,
        )

        if configuration is None:
            raise not_found("System configuration")

        return configuration

    def update(
        self,
        *,
        configuration_id: UUID,
        data: SystemConfigurationUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SystemConfiguration:
        configuration = self.repository.get_by_id(
            configuration_id,
            for_update=True,
        )

        if configuration is None:
            raise not_found("System configuration")

        try:
            validated_value = validate_configuration(
                key=configuration.key,
                category=configuration.category,
                value=data.value,
            )
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        if validated_value == configuration.value:
            raise bad_request(
                "The configuration value has not changed.",
            )

        configuration.value = validated_value
        configuration.updated_by = user_id
        configuration.updated_at = utc_now()

        self.repository.update(configuration)

        self.audit_service.log_event(
            event_type=AuditEventType.SYSTEM_CONFIGURATION_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="system_configuration",
            resource_id=configuration.id,
        )

        self.db.commit()
        self.db.refresh(configuration)

        return configuration

    def update_status(
        self,
        *,
        configuration_id: UUID,
        status: SystemConfigurationStatus,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SystemConfiguration:
        configuration = self.repository.get_by_id(
            configuration_id,
            for_update=True,
        )

        if configuration is None:
            raise not_found("System configuration")

        if configuration.status == status:
            raise bad_request(
                "The configuration is already in the requested status.",
            )

        configuration.status = status
        configuration.updated_by = user_id
        configuration.updated_at = utc_now()

        self.repository.update(configuration)

        self.audit_service.log_event(
            event_type=AuditEventType.SYSTEM_CONFIGURATION_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="system_configuration",
            resource_id=configuration.id,
        )

        self.db.commit()
        self.db.refresh(configuration)

        return configuration

    def get_history(
        self,
        configuration_id: UUID,
    ) -> list[AuditLog]:
        self.get_by_id(configuration_id)

        return self.repository.get_audit_history(
            configuration_id,
        )
