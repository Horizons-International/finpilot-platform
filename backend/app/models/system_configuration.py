import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import (
    SystemConfigurationCategory,
    SystemConfigurationStatus,
)


class SystemConfiguration(Base):
    __tablename__ = "system_configurations"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
    )

    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    category: Mapped[SystemConfigurationCategory] = mapped_column(
        Enum(
            SystemConfigurationCategory,
            name="system_configuration_category",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[SystemConfigurationStatus] = mapped_column(
        Enum(
            SystemConfigurationStatus,
            name="system_configuration_status",
        ),
        nullable=False,
        default=SystemConfigurationStatus.ACTIVE,
        server_default=SystemConfigurationStatus.ACTIVE.value,
        index=True,
    )

    updated_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    updated_by_user = relationship(
        "User",
        foreign_keys=[updated_by],
    )
