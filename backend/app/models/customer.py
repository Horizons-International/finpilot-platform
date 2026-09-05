import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.customer_address import CustomerAddress
    from app.models.customer_contact import CustomerContact

from app.core.database import Base
from app.utils.enums import CustomerStatus


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    middle_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    date_of_birth: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    nationality: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country_of_residence: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    phone_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[CustomerStatus] = mapped_column(
        SQLAlchemyEnum(CustomerStatus, name="customer_status"),
        nullable=False,
        default=CustomerStatus.NEW,
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

    addresses: Mapped[list["CustomerAddress"]] = relationship(
        "CustomerAddress",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    contacts: Mapped[list["CustomerContact"]] = relationship(
        "CustomerContact",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    verification_cases = relationship(
        "IdentityVerificationCase",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
