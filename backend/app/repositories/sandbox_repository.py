"""Persistence operations for sandbox-only records.

Every lookup is scoped to a sandbox account or a one-way API-key hash. No query
in this repository reads or writes the production customer, user, tenant, API-key
or webhook tables.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sandbox import (
    SandboxAccount,
    SandboxAPIKey,
    SandboxCustomer,
    SandboxUser,
    SandboxVerification,
    SandboxWebhook,
    SandboxWebhookEvent,
)


class SandboxRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, record):
        self.db.add(record)
        self.db.flush()
        return record

    def get_account(self, account_id: UUID) -> SandboxAccount | None:
        statement = select(SandboxAccount).where(SandboxAccount.id == account_id)
        return self.db.scalar(statement)

    def get_user_by_email(self, account_id: UUID, email: str) -> SandboxUser | None:
        statement = select(SandboxUser).where(
            SandboxUser.sandbox_account_id == account_id,
            SandboxUser.email == email,
        )
        return self.db.scalar(statement)

    def list_users(self, account_id: UUID) -> list[SandboxUser]:
        statement = (
            select(SandboxUser)
            .where(SandboxUser.sandbox_account_id == account_id)
            .order_by(SandboxUser.created_at.asc())
        )
        return list(self.db.scalars(statement).all())

    def get_key_by_hash(self, key_hash: str) -> SandboxAPIKey | None:
        statement = select(SandboxAPIKey).where(SandboxAPIKey.key_hash == key_hash)
        return self.db.scalar(statement)

    def get_key(self, account_id: UUID, key_id: UUID) -> SandboxAPIKey | None:
        statement = select(SandboxAPIKey).where(
            SandboxAPIKey.sandbox_account_id == account_id,
            SandboxAPIKey.id == key_id,
        )
        return self.db.scalar(statement)

    def list_keys(self, account_id: UUID) -> list[SandboxAPIKey]:
        statement = (
            select(SandboxAPIKey)
            .where(SandboxAPIKey.sandbox_account_id == account_id)
            .order_by(SandboxAPIKey.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_customer(
        self, account_id: UUID, customer_id: UUID
    ) -> SandboxCustomer | None:
        statement = select(SandboxCustomer).where(
            SandboxCustomer.sandbox_account_id == account_id,
            SandboxCustomer.id == customer_id,
        )
        return self.db.scalar(statement)

    def list_customers(self, account_id: UUID, limit: int) -> list[SandboxCustomer]:
        statement = (
            select(SandboxCustomer)
            .where(SandboxCustomer.sandbox_account_id == account_id)
            .order_by(SandboxCustomer.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def get_verification(
        self, account_id: UUID, verification_id: UUID
    ) -> SandboxVerification | None:
        statement = select(SandboxVerification).where(
            SandboxVerification.sandbox_account_id == account_id,
            SandboxVerification.id == verification_id,
        )
        return self.db.scalar(statement)

    def get_webhook(self, account_id: UUID, webhook_id: UUID) -> SandboxWebhook | None:
        statement = select(SandboxWebhook).where(
            SandboxWebhook.sandbox_account_id == account_id,
            SandboxWebhook.id == webhook_id,
        )
        return self.db.scalar(statement)

    def list_webhooks(self, account_id: UUID) -> list[SandboxWebhook]:
        statement = (
            select(SandboxWebhook)
            .where(SandboxWebhook.sandbox_account_id == account_id)
            .order_by(SandboxWebhook.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def list_webhook_events(
        self, account_id: UUID, webhook_id: UUID, limit: int
    ) -> list[SandboxWebhookEvent]:
        statement = (
            select(SandboxWebhookEvent)
            .where(
                SandboxWebhookEvent.sandbox_account_id == account_id,
                SandboxWebhookEvent.webhook_id == webhook_id,
            )
            .order_by(SandboxWebhookEvent.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())
