"""Isolated sandbox-only organizations, users, customers and simulations.

These models deliberately do not use production ``Tenant``, ``User``,
``Customer``, ``APIKey`` or webhook tables. Sandbox records are scoped by
``sandbox_account_id`` in every repository query.
"""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SandboxAccount(Base):
    __tablename__ = "sandbox_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED')",
            name="ck_sandbox_accounts_status",
        ),
        Index("ix_sandbox_accounts_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_name: Mapped[str] = mapped_column(String(200), nullable=False)
    developer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    developer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    organization: Mapped["SandboxOrganization"] = relationship(
        back_populates="account", uselist=False, cascade="all, delete-orphan"
    )
    users: Mapped[list["SandboxUser"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["SandboxAPIKey"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    customers: Mapped[list["SandboxCustomer"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    webhooks: Mapped[list["SandboxWebhook"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class SandboxOrganization(Base):
    __tablename__ = "sandbox_organizations"
    __table_args__ = (
        UniqueConstraint("sandbox_account_id", name="uq_sandbox_organizations_account"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[SandboxAccount] = relationship(back_populates="organization")


class SandboxUser(Base):
    __tablename__ = "sandbox_users"
    __table_args__ = (
        UniqueConstraint(
            "sandbox_account_id", "email", name="uq_sandbox_users_account_email"
        ),
        CheckConstraint(
            "role IN ('DEVELOPER', 'OPERATOR', 'REVIEWER', 'AUDITOR')",
            name="ck_sandbox_users_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="DEVELOPER"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[SandboxAccount] = relationship(back_populates="users")


class SandboxAPIKey(Base):
    __tablename__ = "sandbox_api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_sandbox_api_keys_hash"),
        CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')", name="ck_sandbox_api_keys_status"
        ),
        Index("ix_sandbox_api_keys_account_status", "sandbox_account_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    account: Mapped[SandboxAccount] = relationship(back_populates="api_keys")


class SandboxCustomer(Base):
    __tablename__ = "sandbox_customers"
    __table_args__ = (
        UniqueConstraint(
            "sandbox_account_id",
            "external_reference",
            name="uq_sandbox_customers_account_reference",
        ),
        UniqueConstraint(
            "id", "sandbox_account_id", name="uq_sandbox_customers_id_account"
        ),
        Index(
            "ix_sandbox_customers_account_created",
            "sandbox_account_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="NEW"
    )
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[SandboxAccount] = relationship(back_populates="customers")
    verifications: Mapped[list["SandboxVerification"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class SandboxVerification(Base):
    __tablename__ = "sandbox_verifications"
    __table_args__ = (
        CheckConstraint(
            "scenario IN ('APPROVED', 'REJECTED', 'MANUAL_REVIEW')",
            name="ck_sandbox_verifications_scenario",
        ),
        CheckConstraint(
            "status IN ('VERIFIED', 'REJECTED', 'REVIEW_REQUIRED')",
            name="ck_sandbox_verifications_status",
        ),
        Index(
            "ix_sandbox_verifications_account_created",
            "sandbox_account_id",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["customer_id", "sandbox_account_id"],
            ["sandbox_customers.id", "sandbox_customers.sandbox_account_id"],
            ondelete="CASCADE",
            name="fk_sandbox_verifications_customer_account",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    scenario: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer: Mapped[SandboxCustomer] = relationship(back_populates="verifications")


class SandboxWebhook(Base):
    __tablename__ = "sandbox_webhooks"
    __table_args__ = (
        Index(
            "ix_sandbox_webhooks_account_created",
            "sandbox_account_id",
            "created_at",
        ),
        UniqueConstraint(
            "id", "sandbox_account_id", name="uq_sandbox_webhooks_id_account"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    event_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[SandboxAccount] = relationship(back_populates="webhooks")
    events: Mapped[list["SandboxWebhookEvent"]] = relationship(
        back_populates="webhook", cascade="all, delete-orphan"
    )


class SandboxWebhookEvent(Base):
    __tablename__ = "sandbox_webhook_events"
    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('SIMULATED_NOT_SENT')",
            name="ck_sandbox_webhook_events_delivery_status",
        ),
        Index("ix_sandbox_webhook_events_webhook_created", "webhook_id", "created_at"),
        ForeignKeyConstraint(
            ["webhook_id", "sandbox_account_id"],
            ["sandbox_webhooks.id", "sandbox_webhooks.sandbox_account_id"],
            ondelete="CASCADE",
            name="fk_sandbox_webhook_events_webhook_account",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sandbox_account_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sandbox_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    webhook_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="SIMULATED_NOT_SENT"
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    webhook: Mapped[SandboxWebhook] = relationship(back_populates="events")
