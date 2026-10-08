import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import (
    ReportExportFormat,
    ReportExportStatus,
    ReportType,
)


class ReportExport(Base):
    __tablename__ = "report_exports"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    report_type: Mapped[ReportType] = mapped_column(
        Enum(
            ReportType,
            name="report_type",
        ),
        nullable=False,
        index=True,
    )

    format: Mapped[ReportExportFormat] = mapped_column(
        Enum(
            ReportExportFormat,
            name="report_export_format",
        ),
        nullable=False,
    )

    requested_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    filters: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    status: Mapped[ReportExportStatus] = mapped_column(
        Enum(
            ReportExportStatus,
            name="report_export_status",
        ),
        nullable=False,
        default=ReportExportStatus.REQUESTED,
        server_default=ReportExportStatus.REQUESTED.value,
        index=True,
    )

    filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    storage_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    row_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    tenant = relationship(
        "Tenant",
        back_populates="report_exports",
    )
