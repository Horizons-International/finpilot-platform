"""Native-async tenant system configuration operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.system_configuration import SystemConfiguration
from app.models.user import User
from app.schemas.system_configuration import (
    SystemConfigurationCreate,
    SystemConfigurationUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.services.async_tenant_access_audit import deny_tenant_access
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    SystemConfigurationCategory,
    SystemConfigurationStatus,
)
from app.utils.errors import bad_request
from app.utils.validators.system_configuration import validate_configuration


class AsyncSystemConfigurationService:
    """Perform tenant-bound configuration reads and audited writes."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "Configuration tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.audit = AsyncAuditService(db)

    async def _validate_updater(self, user_id: UUID) -> None:
        exists = await self.db.scalar(
            select(User.id).where(User.id == user_id, User.tenant_id == self.tenant_id)
        )
        if exists is None:
            raise ValueError(
                "Configuration updater does not belong to the current tenant."
            )

    async def _get(
        self, configuration_id: UUID, *, for_update: bool = False
    ) -> SystemConfiguration:
        statement = select(SystemConfiguration).where(
            SystemConfiguration.id == configuration_id,
            SystemConfiguration.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        configuration = await self.db.scalar(statement)
        if configuration is None:
            await deny_tenant_access(
                self.db,
                resource_type="system_configuration",
                resource_id=configuration_id,
                resource_name="System configuration",
            )
        return configuration

    async def create(
        self,
        *,
        data: SystemConfigurationCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SystemConfiguration:
        key = data.key.strip()
        try:
            value = validate_configuration(
                key=key, category=data.category, value=data.value
            )
        except ValueError as exc:
            raise bad_request(str(exc)) from exc
        await self._validate_updater(user_id)
        existing = await self.db.scalar(
            select(SystemConfiguration.id).where(
                SystemConfiguration.tenant_id == self.tenant_id,
                SystemConfiguration.key == key,
            )
        )
        if existing is not None:
            raise bad_request("A system configuration with this key already exists.")

        configuration = SystemConfiguration(
            tenant_id=self.tenant_id,
            key=key,
            value=value,
            category=data.category,
            status=data.status,
            updated_by=user_id,
            updated_at=utc_now(),
        )
        self.db.add(configuration)
        try:
            await self.db.flush()
            await self.audit.log_event(
                event_type=AuditEventType.SYSTEM_CONFIGURATION_CREATED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="system_configuration",
                resource_id=configuration.id,
            )
            await self.db.commit()
            await self.db.refresh(configuration)
            return configuration
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request(
                "A system configuration with this key already exists."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def list_all(
        self,
        *,
        category: SystemConfigurationCategory | None = None,
        status: SystemConfigurationStatus | None = None,
    ) -> list[SystemConfiguration]:
        statement = select(SystemConfiguration).where(
            SystemConfiguration.tenant_id == self.tenant_id
        )
        if category is not None:
            statement = statement.where(SystemConfiguration.category == category)
        if status is not None:
            statement = statement.where(SystemConfiguration.status == status)
        result = await self.db.scalars(
            statement.order_by(SystemConfiguration.key.asc())
        )
        return list(result.all())

    async def get_by_id(self, configuration_id: UUID) -> SystemConfiguration:
        return await self._get(configuration_id)

    async def update(
        self,
        *,
        configuration_id: UUID,
        data: SystemConfigurationUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SystemConfiguration:
        configuration = await self._get(configuration_id, for_update=True)
        await self._validate_updater(user_id)
        try:
            value = validate_configuration(
                key=configuration.key,
                category=configuration.category,
                value=data.value,
            )
        except ValueError as exc:
            raise bad_request(str(exc)) from exc
        if value == configuration.value:
            raise bad_request("The configuration value has not changed.")
        configuration.value = value
        configuration.updated_by = user_id
        configuration.updated_at = utc_now()
        await self.audit.log_event(
            event_type=AuditEventType.SYSTEM_CONFIGURATION_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="system_configuration",
            resource_id=configuration.id,
        )
        await self.db.commit()
        await self.db.refresh(configuration)
        return configuration

    async def update_status(
        self,
        *,
        configuration_id: UUID,
        status: SystemConfigurationStatus,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SystemConfiguration:
        configuration = await self._get(configuration_id, for_update=True)
        await self._validate_updater(user_id)
        if configuration.status == status:
            raise bad_request("The configuration is already in the requested status.")
        configuration.status = status
        configuration.updated_by = user_id
        configuration.updated_at = utc_now()
        await self.audit.log_event(
            event_type=AuditEventType.SYSTEM_CONFIGURATION_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="system_configuration",
            resource_id=configuration.id,
        )
        await self.db.commit()
        await self.db.refresh(configuration)
        return configuration

    async def get_history(self, configuration_id: UUID) -> list[AuditLog]:
        await self._get(configuration_id)
        result = await self.db.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == self.tenant_id,
                AuditLog.resource_type == "system_configuration",
                AuditLog.resource_id == configuration_id,
            )
            .order_by(AuditLog.timestamp.desc())
        )
        return list(result.all())
