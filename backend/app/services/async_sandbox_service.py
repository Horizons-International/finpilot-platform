"""Native-async sandbox operations; never call production providers or models."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sandbox import (
    SandboxAccount,
    SandboxAPIKey,
    SandboxCustomer,
    SandboxOrganization,
    SandboxUser,
    SandboxVerification,
    SandboxWebhook,
    SandboxWebhookEvent,
)
from app.repositories.async_sandbox_repository import AsyncSandboxRepository
from app.schemas.sandbox import (
    SandboxAccountCreate,
    SandboxAPIKeyCreate,
    SandboxCustomerCreate,
    SandboxUserCreate,
    SandboxVerificationCreate,
    SandboxWebhookCreate,
    SandboxWebhookSimulationRequest,
)
from app.utils.date_time import utc_now

ALLOWED_SCOPES = {
    "sandbox:read",
    "sandbox:write",
    "sandbox:webhooks",
    "sandbox:admin",
}


def not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Sandbox {resource} not found.",
    )


class AsyncSandboxService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = AsyncSandboxRepository(db)

    @staticmethod
    def _new_api_key() -> str:
        return f"fp_test_{secrets.token_urlsafe(32)}"

    @staticmethod
    def _key_hash(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def _create_key(
        self, account_id: UUID, name: str, permissions: list[str]
    ) -> tuple[SandboxAPIKey, str]:
        raw_key = self._new_api_key()
        key = SandboxAPIKey(
            sandbox_account_id=account_id,
            name=name,
            key_prefix=raw_key[:18],
            key_hash=self._key_hash(raw_key),
            permissions=permissions,
            status="ACTIVE",
        )
        await self.repository.create(key)
        return key, raw_key

    async def create_account(self, payload: SandboxAccountCreate) -> dict[str, Any]:
        account = SandboxAccount(
            organization_name=payload.organization_name,
            developer_name=payload.developer_name,
            developer_email=str(payload.developer_email).lower(),
            status="ACTIVE",
            expires_at=utc_now() + timedelta(days=30),
        )
        await self.repository.create(account)
        organization = SandboxOrganization(
            sandbox_account_id=account.id,
            name=payload.organization_name,
            code=f"SBX-{uuid4().hex[:12].upper()}",
        )
        developer = SandboxUser(
            sandbox_account_id=account.id,
            name=payload.developer_name,
            email=str(payload.developer_email).lower(),
            role="DEVELOPER",
        )
        await self.repository.create(organization)
        await self.repository.create(developer)
        initial_key, raw_key = await self._create_key(
            account.id,
            "Initial sandbox key",
            ["sandbox:admin", "sandbox:read", "sandbox:write", "sandbox:webhooks"],
        )
        sample_customers = [
            SandboxCustomer(
                sandbox_account_id=account.id,
                external_reference="SAMPLE-001",
                first_name="Alex",
                last_name="Morgan",
                email="alex.morgan@example.com",
                phone_number="+15550101001",
                status="NEW",
                attributes={"source": "seeded_sandbox_data", "segment": "retail"},
            ),
            SandboxCustomer(
                sandbox_account_id=account.id,
                external_reference="SAMPLE-002",
                first_name="Jordan",
                last_name="Lee",
                email="jordan.lee@example.com",
                phone_number="+15550101002",
                status="PENDING_VERIFICATION",
                attributes={
                    "source": "seeded_sandbox_data",
                    "segment": "small_business",
                },
            ),
            SandboxCustomer(
                sandbox_account_id=account.id,
                external_reference="SAMPLE-003",
                first_name="Taylor",
                last_name="Reed",
                email="taylor.reed@example.com",
                phone_number="+15550101003",
                status="VERIFIED",
                attributes={"source": "seeded_sandbox_data", "segment": "retail"},
            ),
        ]
        self.db.add_all(sample_customers)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(account)
        await self.db.refresh(organization)
        await self.db.refresh(developer)
        await self.db.refresh(initial_key)
        for customer in sample_customers:
            await self.db.refresh(customer)
        return {
            "account": account,
            "organization": organization,
            "developer": developer,
            "api_key": raw_key,
            "sample_customers": sample_customers,
        }

    async def get_account(self, account_id: UUID) -> SandboxAccount:
        account = await self.repository.get_account(account_id)
        if (
            account is None
            or account.status != "ACTIVE"
            or account.expires_at <= utc_now()
        ):
            raise not_found("account")
        return account

    async def list_users(self, account_id: UUID) -> list[SandboxUser]:
        await self.get_account(account_id)
        return await self.repository.list_users(account_id)

    async def create_user(
        self, account_id: UUID, payload: SandboxUserCreate
    ) -> SandboxUser:
        await self.get_account(account_id)
        normalized_email = str(payload.email).lower()
        existing = await self.repository.get_user_by_email(account_id, normalized_email)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="A sandbox user with this email already exists in the account.",
            )
        user = SandboxUser(
            sandbox_account_id=account_id,
            name=payload.name,
            email=normalized_email,
            role=payload.role,
        )
        await self.repository.create(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create_api_key(
        self, account_id: UUID, payload: SandboxAPIKeyCreate
    ) -> tuple[SandboxAPIKey, str]:
        invalid = sorted(set(payload.permissions) - ALLOWED_SCOPES)
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=(f"Unsupported sandbox permissions: {', '.join(invalid)}"),
            )
        await self.get_account(account_id)
        key, raw_key = await self._create_key(
            account_id, payload.name, list(payload.permissions)
        )
        await self.db.commit()
        await self.db.refresh(key)
        return key, raw_key

    async def list_api_keys(self, account_id: UUID) -> list[SandboxAPIKey]:
        await self.get_account(account_id)
        return await self.repository.list_keys(account_id)

    async def revoke_api_key(self, account_id: UUID, key_id: UUID) -> SandboxAPIKey:
        await self.get_account(account_id)
        key = await self.repository.get_key(account_id, key_id)
        if key is None:
            raise not_found("API key")
        if key.status != "REVOKED":
            if "sandbox:admin" in set(key.permissions or []):
                keys = await self.repository.list_keys(account_id)
                active_admin_keys = [
                    candidate
                    for candidate in keys
                    if candidate.status == "ACTIVE"
                    and "sandbox:admin" in set(candidate.permissions or [])
                ]
                if len(active_admin_keys) <= 1:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Cannot revoke the last active sandbox admin key. "
                            "Create another admin key first."
                        ),
                    )
            key.status = "REVOKED"
            key.revoked_at = utc_now()
            await self.db.commit()
            await self.db.refresh(key)
        return key

    async def list_customers(
        self, account_id: UUID, limit: int
    ) -> list[SandboxCustomer]:
        await self.get_account(account_id)
        return await self.repository.list_customers(account_id, limit)

    async def create_customer(
        self, account_id: UUID, payload: SandboxCustomerCreate
    ) -> SandboxCustomer:
        await self.get_account(account_id)
        customer = SandboxCustomer(
            sandbox_account_id=account_id,
            external_reference=(
                payload.external_reference or f"SBX-{uuid4().hex[:12].upper()}"
            ),
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=str(payload.email).lower(),
            phone_number=payload.phone_number,
            status="NEW",
            attributes=payload.attributes,
        )
        await self.repository.create(customer)
        await self._record_events(
            account_id,
            event_type="customer.created",
            data={
                "customer_id": str(customer.id),
                "external_reference": customer.external_reference,
                "status": customer.status,
            },
        )
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def get_customer(
        self, account_id: UUID, customer_id: UUID
    ) -> SandboxCustomer:
        await self.get_account(account_id)
        customer = await self.repository.get_customer(account_id, customer_id)
        if customer is None:
            raise not_found("customer")
        return customer

    async def create_verification(
        self, account_id: UUID, customer_id: UUID, payload: SandboxVerificationCreate
    ) -> SandboxVerification:
        customer = await self.get_customer(account_id, customer_id)
        result_map = {
            "APPROVED": ("VERIFIED", "Mock verification passed."),
            "REJECTED": ("REJECTED", "Mock verification did not pass."),
            "MANUAL_REVIEW": (
                "REVIEW_REQUIRED",
                "Mock verification requires manual review.",
            ),
        }
        verification_status, message = result_map[payload.scenario]
        verification = SandboxVerification(
            sandbox_account_id=account_id,
            customer_id=customer.id,
            scenario=payload.scenario,
            status=verification_status,
            result={
                "provider": "FINPILOT_SANDBOX_MOCK",
                "simulated": True,
                "message": message,
                "checks": {
                    "identity_document": verification_status == "VERIFIED",
                    "watchlist": (
                        "not_performed"
                        if payload.scenario == "MANUAL_REVIEW"
                        else (
                            "clear"
                            if verification_status == "VERIFIED"
                            else "potential_match"
                        )
                    ),
                },
            },
        )
        await self.repository.create(verification)
        customer.status = verification_status
        event_type = (
            "verification.failed"
            if payload.scenario == "REJECTED"
            else "verification.completed"
        )
        await self._record_events(
            account_id,
            event_type=event_type,
            data={
                "customer_id": str(customer.id),
                "verification_status": verification_status,
                "verification_id": str(verification.id),
            },
        )
        await self.db.commit()
        await self.db.refresh(verification)
        return verification

    async def get_verification(
        self, account_id: UUID, verification_id: UUID
    ) -> SandboxVerification:
        await self.get_account(account_id)
        result = await self.repository.get_verification(account_id, verification_id)
        if result is None:
            raise not_found("verification")
        return result

    async def create_webhook(
        self, account_id: UUID, payload: SandboxWebhookCreate
    ) -> SandboxWebhook:
        await self.get_account(account_id)
        webhook = SandboxWebhook(
            sandbox_account_id=account_id,
            name=payload.name,
            endpoint_url=str(payload.endpoint_url) if payload.endpoint_url else None,
            event_types=payload.event_types,
            status="ACTIVE",
        )
        await self.repository.create(webhook)
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def list_webhooks(self, account_id: UUID) -> list[SandboxWebhook]:
        await self.get_account(account_id)
        return await self.repository.list_webhooks(account_id)

    async def simulate_webhook(
        self,
        account_id: UUID,
        webhook_id: UUID,
        payload: SandboxWebhookSimulationRequest,
    ) -> SandboxWebhookEvent:
        await self.get_account(account_id)
        webhook = await self.repository.get_webhook(account_id, webhook_id)
        if webhook is None:
            raise not_found("webhook")
        if webhook.status != "ACTIVE":
            raise HTTPException(
                status_code=409, detail="Sandbox webhook is not active."
            )
        if payload.event_type not in set(webhook.event_types or []):
            raise HTTPException(
                status_code=422,
                detail=("This event type is not subscribed by the sandbox webhook."),
            )
        data: dict[str, Any] = {
            "sandbox": True,
            "organization_id": str(account_id),
            "message": "Synthetic sandbox event; no production data is included.",
        }
        if payload.customer_id is not None:
            customer = await self.get_customer(account_id, payload.customer_id)
            data["customer"] = {
                "id": str(customer.id),
                "external_reference": customer.external_reference,
                "status": customer.status,
            }
        event = await self._record_one_event(webhook, payload.event_type, data)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_webhook_events(
        self, account_id: UUID, webhook_id: UUID, limit: int
    ) -> list[SandboxWebhookEvent]:
        await self.get_account(account_id)
        if await self.repository.get_webhook(account_id, webhook_id) is None:
            raise not_found("webhook")
        return await self.repository.list_webhook_events(account_id, webhook_id, limit)

    async def _record_events(
        self, account_id: UUID, *, event_type: str, data: dict[str, Any]
    ) -> None:
        result = await self.db.scalars(
            select(SandboxWebhook).where(
                SandboxWebhook.sandbox_account_id == account_id,
                SandboxWebhook.status == "ACTIVE",
            )
        )
        for webhook in result.all():
            if event_type in set(webhook.event_types or []):
                await self._record_one_event(
                    webhook, event_type, {"sandbox": True, **data}
                )

    async def _record_one_event(
        self, webhook: SandboxWebhook, event_type: str, data: dict[str, Any]
    ) -> SandboxWebhookEvent:
        event_id = uuid4()
        event = SandboxWebhookEvent(
            id=event_id,
            sandbox_account_id=webhook.sandbox_account_id,
            webhook_id=webhook.id,
            event_type=event_type,
            delivery_status="SIMULATED_NOT_SENT",
            payload={
                "id": str(event_id),
                "type": event_type,
                "created_at": utc_now().isoformat(),
                "data": {"sandbox": True, **data},
            },
        )
        await self.repository.create(event)
        return event
