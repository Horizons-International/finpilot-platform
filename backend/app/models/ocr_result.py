import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import OCRProcessingStatus


class OCRResult(Base):
    __tablename__ = "ocr_results"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "customer_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    request_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )

    extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[OCRProcessingStatus] = mapped_column(
        SQLEnum(
            OCRProcessingStatus,
            name="ocr_processing_status",
        ),
        nullable=False,
        default=OCRProcessingStatus.SUBMITTED,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    document = relationship(
        "CustomerDocument",
        back_populates="ocr_results",
    )
