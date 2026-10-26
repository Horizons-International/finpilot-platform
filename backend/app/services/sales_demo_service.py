"""Seed and manage sales-demo scenarios without calling production services."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.sandbox import (
    SandboxAccount,
    SandboxCustomer,
    SandboxVerification,
    SandboxWebhookEvent,
)
from app.models.sandbox_demo import SandboxDemoRecord
from app.schemas.sales_demo import SalesDemoRecordType
from app.schemas.sandbox import SandboxAccountCreate
from app.services.sales_demo_fixtures import (
    CUSTOMER_SEEDS,
    RECORD_SEEDS,
    SCENARIO_CATALOG,
)
from app.services.sandbox_service import SandboxService


class SalesDemoService:
    """All mutations are scoped to a sandbox account ID and demo-only tables."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sandbox = SandboxService(db)

    def create_account(self, payload: SandboxAccountCreate) -> dict[str, Any]:
        """Create a sandbox account then replace starter examples with sales data."""
        created = self.sandbox.create_account(payload)
        account_id = created["account"].id
        try:
            dashboard = self.reset_demo_data(account_id)
            customers = list(
                self.db.scalars(
                    select(SandboxCustomer)
                    .where(SandboxCustomer.sandbox_account_id == account_id)
                    .order_by(SandboxCustomer.external_reference.asc())
                ).all()
            )
        except Exception:
            self.db.rollback()
            account = self.db.scalar(
                select(SandboxAccount).where(SandboxAccount.id == account_id)
            )
            if account is not None:
                self.db.delete(account)
                self.db.commit()
            raise
        created["sample_customers"] = customers
        created["dashboard"] = dashboard
        created["scenario_keys"] = [item["key"] for item in SCENARIO_CATALOG]
        return created

    def reset_demo_data(self, account_id: UUID) -> dict[str, Any]:
        """Destructively reset one account's demo customers/events/records only.

        The sandbox account, its organization, sandbox users, API keys and webhook
        subscriptions are retained. Production entities and other sandbox accounts
        are never queried for mutation.
        """
        self.sandbox.get_account(account_id)

        records = self.db.scalars(
            select(SandboxDemoRecord).where(
                SandboxDemoRecord.sandbox_account_id == account_id
            )
        ).all()
        for record in records:
            self.db.delete(record)

        webhook_events = self.db.scalars(
            select(SandboxWebhookEvent).where(
                SandboxWebhookEvent.sandbox_account_id == account_id
            )
        ).all()
        for event in webhook_events:
            self.db.delete(event)

        customers = self.db.scalars(
            select(SandboxCustomer).where(
                SandboxCustomer.sandbox_account_id == account_id
            )
        ).all()
        for customer in customers:
            self.db.delete(customer)
        self.db.flush()

        customers_by_ref: dict[str, SandboxCustomer] = {}
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
            self.db.flush()
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
        for customer_ref, scenario, verification_status, message in verification_specs:
            customer = customers_by_ref[customer_ref]
            self.db.add(
                SandboxVerification(
                    sandbox_account_id=account_id,
                    customer_id=customer.id,
                    scenario=scenario,
                    status=verification_status,
                    result={
                        "message": message,
                        "provider": "static_demo_fixture",
                        "external_provider_called": False,
                        "is_synthetic": True,
                    },
                )
            )

        for seed in RECORD_SEEDS:
            seed_customer_ref = seed.get("customer_ref")
            if seed_customer_ref is not None:
                if not isinstance(seed_customer_ref, str):
                    raise ValueError("Seed customer_ref must be a string.")

                customer_ref = seed_customer_ref
            customer_id = (
                customers_by_ref[customer_ref].id if customer_ref is not None else None
            )
            self.db.add(
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
        self.db.commit()
        return self.get_dashboard(account_id)

    def get_dashboard(self, account_id: UUID) -> dict[str, Any]:
        self.sandbox.get_account(account_id)
        customers = list(
            self.db.scalars(
                select(SandboxCustomer).where(
                    SandboxCustomer.sandbox_account_id == account_id
                )
            ).all()
        )
        verification_count = int(
            self.db.scalar(
                select(func.count(SandboxVerification.id)).where(
                    SandboxVerification.sandbox_account_id == account_id
                )
            )
            or 0
        )
        verified_count = int(
            self.db.scalar(
                select(func.count(SandboxVerification.id)).where(
                    SandboxVerification.sandbox_account_id == account_id,
                    SandboxVerification.status == "VERIFIED",
                )
            )
            or 0
        )
        type_counts = {
            row[0]: int(row[1])
            for row in self.db.execute(
                select(
                    SandboxDemoRecord.record_type,
                    func.count(SandboxDemoRecord.id),
                )
                .where(SandboxDemoRecord.sandbox_account_id == account_id)
                .group_by(SandboxDemoRecord.record_type)
            ).all()
        }
        record_count = int(
            self.db.scalar(
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

    def list_verifications(
        self, account_id: UUID, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List only the verification examples owned by this sandbox account."""
        self.sandbox.get_account(account_id)
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
            for verification, external_reference in self.db.execute(statement).all()
        ]

    def list_records(
        self,
        account_id: UUID,
        *,
        record_type: SalesDemoRecordType | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.sandbox.get_account(account_id)
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
        output: list[dict[str, Any]] = []
        for record, external_reference in self.db.execute(statement).all():
            output.append(
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
            )
        return output

    def list_catalog(self) -> list[dict[str, Any]]:
        return [dict(item) for item in SCENARIO_CATALOG]
