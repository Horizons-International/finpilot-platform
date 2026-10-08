import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import UserRole, UserStatus


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    phone_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    role: Mapped[UserRole] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    department: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
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

    verification_reviews = relationship(
        "VerificationReview",
        back_populates="reviewer",
    )

    assigned_verification_cases = relationship(
        "IdentityVerificationCase",
        foreign_keys="IdentityVerificationCase.assigned_to",
        back_populates="assigned_reviewer",
    )

    assigned_compliance_cases = relationship(
        "ComplianceCase",
        foreign_keys="ComplianceCase.assigned_to",
        back_populates="assigned_user",
    )

    compliance_case_history = relationship(
        "ComplianceCaseHistory",
        foreign_keys="ComplianceCaseHistory.changed_by",
        back_populates="changed_by_user",
    )

    tenant = relationship(
        "Tenant",
        back_populates="users",
    )
