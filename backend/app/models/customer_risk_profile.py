import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import CustomerRiskLevel


class CustomerRiskProfile(Base):
    __tablename__ = "customer_risk_profiles"

    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            name="uq_customer_risk_profiles_customer_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    customer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    risk_level: Mapped[CustomerRiskLevel] = mapped_column(
        Enum(
            CustomerRiskLevel,
            name="customer_risk_level",
        ),
        nullable=False,
        index=True,
    )

    risk_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    risk_category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    assessment_source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    customer = relationship(
        "Customer",
        back_populates="risk_profile",
    )
