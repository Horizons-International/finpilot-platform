"""Async sales-demo scenarios, using synthetic fixtures only."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sandbox import (
    SandboxAccount,
    SandboxCustomer,
    SandboxVerification,
    SandboxWebhookEvent,
)
from app.models.sandbox_demo import SandboxDemoRecord
from app.schemas.sales_demo import SalesDemoRecordType
from app.schemas.sandbox import SandboxAccountCreate
from app.services.async_sandbox_service import AsyncSandboxService
from app.services.sales_demo_fixtures import (
    CUSTOMER_SEEDS,
    RECORD_SEEDS,
    SCENARIO_CATALOG,
)


class AsyncSalesDemoService:
    """All reads and writes are scoped to a sandbox account and demo-only data."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.sandbox = AsyncSandboxService(db)

    async def create_account(self, payload: SandboxAccountCreate) -> dict[str, Any]:
        created = await self.sandbox.create_account(payload)
        account_id = created["account"].id
        try:
            dashboard = await self.reset_demo_data(account_id)
            customers_result = await self.db.scalars(
                select(SandboxCustomer)
                .where(SandboxCustomer.sandbox_account_id == account_id)
                .order_by(SandboxCustomer.external_reference.asc())
            )
            customers = list(customers_result.all())
        except Exception:
            await self.db.rollback()
            account = await self.db.scalar(
                select(SandboxAccount).where(SandboxAccount.id == account_id)
            )
            if account is not None:
                await self.db.delete(account)
                await self.db.commit()
            raise
        created["sample_customers"] = customers
        created["dashboard"] = dashboard
        created["scenario_keys"] = [item["key"] for item in SCENARIO_CATALOG]
        return created

    async def reset_demo_data(self, account_id: UUID) -> dict[str, Any]:
        """Replace only this account's demo customers/events/records.

        Account identity, organization, users, API keys and webhook subscriptions
        are retained. This operation never touches production tables or other
        sandbox accounts.
        """
        await self.sandbox.get_account(account_id)
        for model in (SandboxDemoRecord, SandboxWebhookEvent, SandboxCustomer):
            result = await self.db.scalars(
                select(model).where(model.sandbox_account_id == account_id)
            )
            for row in result.all():
                await self.db.delete(row)
        await self.db.flush()

        customers_by_ref: dict[str, SandboxCustomer] = {}
        customers: list[SandboxCustomer] = []
        for seed in CUSTOMER_SEEDS:
            customer = SandboxCustomer(
                sandbox_account_id=account_id,
                external_reference=seed["external_reference"],
                first_name=seed["first_name"],
                last_name=seed["last_name"],
                email=seed["email"],
                phone_number=seed["phone_number"],
                status=seed["status"],
                attributes=dict(seed["attributes"]),
            )
            self.db.add(customer)
            customers.append(customer)
        await self.db.flush()
        for customer in customers:
            customers_by_ref[customer.external_reference] = customer

        verification_specs = (
            ("DEMO-IND-001", "APPROVED", "VERIFIED", "Mock verification passed."),
            (
                "DEMO-IND-002",
                "MANUAL_REVIEW",
                "REVIEW_REQUIRED",
                "Mock result requires manual review.",
            ),
            ("DEMO-IND-003", "REJECTED", "REJECTED", "Mock verification did not pass."),
            (
                "DEMO-BIZ-001",
                "APPROVED",
                "VERIFIED",
                "Synthetic business verification passed.",
            ),
        )
        self.db.add_all(
            [
                SandboxVerification(
                    sandbox_account_id=account_id,
                    customer_id=customers_by_ref[customer_ref].id,
                    scenario=scenario,
                    status=verification_status,
                    result={
                        "message": message,
                        "provider": "static_demo_fixture",
                        "external_provider_called": False,
                        "is_synthetic": True,
                    },
                )
                for (
                    customer_ref,
                    scenario,
                    verification_status,
                    message,
                ) in verification_specs
            ]
        )

        demo_records: list[SandboxDemoRecord] = []
        for seed in RECORD_SEEDS:
            raw_customer_ref = seed.get("customer_ref")
            if raw_customer_ref is not None and not isinstance(raw_customer_ref, str):
                raise ValueError("Seed customer_ref must be a string.")
            customer_id = (
                customers_by_ref[raw_customer_ref].id
                if isinstance(raw_customer_ref, str)
                else None
            )
            demo_records.append(
                SandboxDemoRecord(
                    sandbox_account_id=account_id,
                    customer_id=customer_id,
                    record_type=seed["record_type"],
                    scenario_key=seed["scenario_key"],
                    title=seed["title"],
                    summary=seed["summary"],
                    data=dict(seed["data"]),
                )
            )
        self.db.add_all(demo_records)
        await self.db.commit()
        return await self.get_dashboard(account_id)

    async def get_dashboard(self, account_id: UUID) -> dict[str, Any]:
        await self.sandbox.get_account(account_id)
        customers_result = await self.db.scalars(
            select(SandboxCustomer).where(
                SandboxCustomer.sandbox_account_id == account_id
            )
        )
        customers = list(customers_result.all())
        verification_count = int(
            await self.db.scalar(
                select(func.count(SandboxVerification.id)).where(
                    SandboxVerification.sandbox_account_id == account_id
                )
            )
            or 0
        )
        verified_count = int(
            await self.db.scalar(
                select(func.count(SandboxVerification.id)).where(
                    SandboxVerification.sandbox_account_id == account_id,
                    SandboxVerification.status == "VERIFIED",
                )
            )
            or 0
        )
        type_count_rows = await self.db.execute(
            select(SandboxDemoRecord.record_type, func.count(SandboxDemoRecord.id))
            .where(SandboxDemoRecord.sandbox_account_id == account_id)
            .group_by(SandboxDemoRecord.record_type)
        )
        type_counts = {row[0]: int(row[1]) for row in type_count_rows.all()}
        record_count = int(
            await self.db.scalar(
                select(func.count(SandboxDemoRecord.id)).where(
                    SandboxDemoRecord.sandbox_account_id == account_id
                )
            )
            or 0
        )
        return {
            "environment": "sales_demo",
            "is_synthetic": True,
            "external_connections_enabled": False,
            "customer_count": len(customers),
            "individual_customer_count": sum(
                1
                for customer in customers
                if (customer.attributes or {}).get("customer_type") == "INDIVIDUAL"
            ),
            "business_customer_count": sum(
                1
                for customer in customers
                if (customer.attributes or {}).get("customer_type") == "BUSINESS"
            ),
            "verification_count": verification_count,
            "verified_count": verified_count,
            "compliance_case_count": type_counts.get("COMPLIANCE_CASE", 0),
            "aml_alert_count": type_counts.get("AML_ALERT", 0),
            "ai_recommendation_count": type_counts.get("AI_RISK_RECOMMENDATION", 0),
            "investigation_summary_count": type_counts.get("INVESTIGATION_SUMMARY", 0),
            "workflow_scenario_count": type_counts.get("WORKFLOW", 0),
            "report_count": type_counts.get("REPORT", 0),
            "scenario_record_count": record_count,
            "usage_sample": {
                "active_users": 146,
                "api_calls": 500000,
                "verification_checks": 25000,
                "ai_requests": 8000,
                "workflow_executions": 1240,
                "reports_generated": 86,
            },
        }

    async def list_verifications(
        self, account_id: UUID, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        await self.sandbox.get_account(account_id)
        statement = (
            select(SandboxVerification, SandboxCustomer.external_reference)
            .join(
                SandboxCustomer,
                (SandboxCustomer.id == SandboxVerification.customer_id)
                & (
                    SandboxCustomer.sandbox_account_id
                    == SandboxVerification.sandbox_account_id
                ),
            )
            .where(SandboxVerification.sandbox_account_id == account_id)
            .order_by(SandboxVerification.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(statement)
        return [
            {
                "id": verification.id,
                "sandbox_account_id": verification.sandbox_account_id,
                "customer_id": verification.customer_id,
                "scenario": verification.scenario,
                "status": verification.status,
                "result": verification.result,
                "created_at": verification.created_at,
                "customer_external_reference": external_reference,
            }
            for verification, external_reference in result.all()
        ]

    async def list_records(
        self,
        account_id: UUID,
        *,
        record_type: SalesDemoRecordType | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        await self.sandbox.get_account(account_id)
        statement = (
            select(SandboxDemoRecord, SandboxCustomer.external_reference)
            .outerjoin(
                SandboxCustomer,
                (SandboxCustomer.id == SandboxDemoRecord.customer_id)
                & (
                    SandboxCustomer.sandbox_account_id
                    == SandboxDemoRecord.sandbox_account_id
                ),
            )
            .where(SandboxDemoRecord.sandbox_account_id == account_id)
            .order_by(
                SandboxDemoRecord.record_type.asc(),
                SandboxDemoRecord.title.asc(),
            )
            .limit(limit)
        )
        if record_type is not None:
            statement = statement.where(
                SandboxDemoRecord.record_type == record_type.value
            )
        result = await self.db.execute(statement)
        return [
            {
                "id": record.id,
                "sandbox_account_id": record.sandbox_account_id,
                "customer_id": record.customer_id,
                "record_type": record.record_type,
                "scenario_key": record.scenario_key,
                "title": record.title,
                "summary": record.summary,
                "data": record.data,
                "created_at": record.created_at,
                "customer_external_reference": external_reference,
            }
            for record, external_reference in result.all()
        ]

    @staticmethod
    def list_catalog() -> list[dict[str, Any]]:
        """Return static fixture data without opening a database connection."""
        return [dict(item) for item in SCENARIO_CATALOG]
