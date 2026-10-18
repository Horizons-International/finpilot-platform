from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.data_protection import EncryptedDate, EncryptedString
from app.core.database import Base
from app.utils.enums import ExtractionReviewStatus, ExtractionStatus


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("customer_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ocr_result_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ocr_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ExtractionStatus] = mapped_column(
        SQLEnum(ExtractionStatus, name="extraction_status"),
        nullable=False,
        default=ExtractionStatus.SUBMITTED,
    )
    review_status: Mapped[ExtractionReviewStatus] = mapped_column(
        SQLEnum(ExtractionReviewStatus, name="extraction_review_status"),
        nullable=False,
        default=ExtractionReviewStatus.PENDING_REVIEW,
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Identity attributes are encrypted at rest and transparently
    # decrypted for authorized application code.
    first_name: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    last_name: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(EncryptedDate(), nullable=True)
    nationality: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    document_number: Mapped[str | None] = mapped_column(
        EncryptedString(), nullable=True
    )
    expiry_date: Mapped[date | None] = mapped_column(EncryptedDate(), nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
