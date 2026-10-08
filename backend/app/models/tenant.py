import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import TenantStatus


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[TenantStatus] = mapped_column(
        Enum(
            TenantStatus,
            name="tenant_status",
        ),
        nullable=False,
        default=TenantStatus.ACTIVE,
        server_default=TenantStatus.ACTIVE.value,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    users = relationship(
        "User",
        back_populates="tenant",
    )

    customers = relationship(
        "Customer",
        back_populates="tenant",
    )

    workflows = relationship(
        "Workflow",
        back_populates="tenant",
    )

    system_configurations = relationship(
        "SystemConfiguration",
        back_populates="tenant",
    )

    report_exports = relationship(
        "ReportExport",
        back_populates="tenant",
    )
