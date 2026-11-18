"""Async persistence for isolated sandbox records only."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sandbox import (
    SandboxAccount,
    SandboxAPIKey,
    SandboxCustomer,
    SandboxUser,
    SandboxVerification,
    SandboxWebhook,
    SandboxWebhookEvent,
)


class AsyncSandboxRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, record):
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_account(self, account_id: UUID) -> SandboxAccount | None:
        return await self.db.scalar(
            select(SandboxAccount).where(SandboxAccount.id == account_id)
        )

    async def get_user_by_email(
        self, account_id: UUID, email: str
    ) -> SandboxUser | None:
        return await self.db.scalar(
            select(SandboxUser).where(
                SandboxUser.sandbox_account_id == account_id,
                SandboxUser.email == email,
            )
        )

    async def list_users(self, account_id: UUID) -> list[SandboxUser]:
        result = await self.db.scalars(
            select(SandboxUser)
            .where(SandboxUser.sandbox_account_id == account_id)
            .order_by(SandboxUser.created_at.asc())
        )
        return list(result.all())

    async def get_key_by_hash(self, key_hash: str) -> SandboxAPIKey | None:
        return await self.db.scalar(
            select(SandboxAPIKey).where(SandboxAPIKey.key_hash == key_hash)
        )

    async def get_key(self, account_id: UUID, key_id: UUID) -> SandboxAPIKey | None:
        return await self.db.scalar(
            select(SandboxAPIKey).where(
                SandboxAPIKey.sandbox_account_id == account_id,
                SandboxAPIKey.id == key_id,
            )
        )

    async def list_keys(self, account_id: UUID) -> list[SandboxAPIKey]:
        result = await self.db.scalars(
            select(SandboxAPIKey)
            .where(SandboxAPIKey.sandbox_account_id == account_id)
            .order_by(SandboxAPIKey.created_at.desc())
        )
        return list(result.all())

    async def get_customer(
        self, account_id: UUID, customer_id: UUID
    ) -> SandboxCustomer | None:
        return await self.db.scalar(
            select(SandboxCustomer).where(
                SandboxCustomer.sandbox_account_id == account_id,
                SandboxCustomer.id == customer_id,
            )
        )

    async def list_customers(
        self, account_id: UUID, limit: int
    ) -> list[SandboxCustomer]:
        result = await self.db.scalars(
            select(SandboxCustomer)
            .where(SandboxCustomer.sandbox_account_id == account_id)
            .order_by(SandboxCustomer.created_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def get_verification(
        self, account_id: UUID, verification_id: UUID
    ) -> SandboxVerification | None:
        return await self.db.scalar(
            select(SandboxVerification).where(
                SandboxVerification.sandbox_account_id == account_id,
                SandboxVerification.id == verification_id,
            )
        )

    async def get_webhook(
        self, account_id: UUID, webhook_id: UUID
    ) -> SandboxWebhook | None:
        return await self.db.scalar(
            select(SandboxWebhook).where(
                SandboxWebhook.sandbox_account_id == account_id,
                SandboxWebhook.id == webhook_id,
            )
        )

    async def list_webhooks(self, account_id: UUID) -> list[SandboxWebhook]:
        result = await self.db.scalars(
            select(SandboxWebhook)
            .where(SandboxWebhook.sandbox_account_id == account_id)
            .order_by(SandboxWebhook.created_at.desc())
        )
        return list(result.all())

    async def list_webhook_events(
        self, account_id: UUID, webhook_id: UUID, limit: int
    ) -> list[SandboxWebhookEvent]:
        result = await self.db.scalars(
            select(SandboxWebhookEvent)
            .where(
                SandboxWebhookEvent.sandbox_account_id == account_id,
                SandboxWebhookEvent.webhook_id == webhook_id,
            )
            .order_by(SandboxWebhookEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.all())
