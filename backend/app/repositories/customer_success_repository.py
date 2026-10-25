"""Persistence layer for customer-success records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.customer_success import (
    CustomerSuccessHistory,
    CustomerSuccessProfile,
    CustomerSuccessSupportInteraction,
    CustomerSuccessUsageSnapshot,
)


class CustomerSuccessRepository:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        current_tenant = db.info.get("tenant_id")
        if current_tenant is not None and current_tenant != tenant_id:
            raise ValueError("The database session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    def get_profile(self, profile_id: UUID) -> CustomerSuccessProfile | None:
        statement = (
            select(CustomerSuccessProfile)
            .where(
                CustomerSuccessProfile.id == profile_id,
                CustomerSuccessProfile.tenant_id == self.tenant_id,
            )
            .options(selectinload(CustomerSuccessProfile.customer_tenant))
        )
        return self.db.scalar(statement)

    def list_profiles(
        self,
        *,
        account_status: str | None = None,
        health_band: str | None = None,
        assigned_manager_id: UUID | None = None,
    ) -> list[CustomerSuccessProfile]:
        statement = (
            select(CustomerSuccessProfile)
            .where(CustomerSuccessProfile.tenant_id == self.tenant_id)
            .options(selectinload(CustomerSuccessProfile.customer_tenant))
            .order_by(CustomerSuccessProfile.updated_at.desc())
        )
        if account_status is not None:
            statement = statement.where(
                CustomerSuccessProfile.account_status == account_status
            )
        if health_band is not None:
            statement = statement.where(
                CustomerSuccessProfile.health_band == health_band
            )
        if assigned_manager_id is not None:
            statement = statement.where(
                CustomerSuccessProfile.assigned_manager_id == assigned_manager_id
            )
        return list(self.db.scalars(statement).all())

    def latest_usage(self, profile_id: UUID) -> CustomerSuccessUsageSnapshot | None:
        statement = (
            select(CustomerSuccessUsageSnapshot)
            .where(
                CustomerSuccessUsageSnapshot.profile_id == profile_id,
                CustomerSuccessUsageSnapshot.tenant_id == self.tenant_id,
            )
            .order_by(
                CustomerSuccessUsageSnapshot.period_start.desc(),
                CustomerSuccessUsageSnapshot.created_at.desc(),
            )
            .limit(1)
        )
        return self.db.scalar(statement)

    def list_usage(self, profile_id: UUID) -> list[CustomerSuccessUsageSnapshot]:
        statement = (
            select(CustomerSuccessUsageSnapshot)
            .where(
                CustomerSuccessUsageSnapshot.profile_id == profile_id,
                CustomerSuccessUsageSnapshot.tenant_id == self.tenant_id,
            )
            .order_by(CustomerSuccessUsageSnapshot.period_start.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_interaction(
        self, profile_id: UUID, interaction_id: UUID
    ) -> CustomerSuccessSupportInteraction | None:
        statement = select(CustomerSuccessSupportInteraction).where(
            CustomerSuccessSupportInteraction.id == interaction_id,
            CustomerSuccessSupportInteraction.profile_id == profile_id,
            CustomerSuccessSupportInteraction.tenant_id == self.tenant_id,
        )
        return self.db.scalar(statement)

    def list_interactions(
        self, profile_id: UUID
    ) -> list[CustomerSuccessSupportInteraction]:
        statement = (
            select(CustomerSuccessSupportInteraction)
            .where(
                CustomerSuccessSupportInteraction.profile_id == profile_id,
                CustomerSuccessSupportInteraction.tenant_id == self.tenant_id,
            )
            .order_by(CustomerSuccessSupportInteraction.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def list_history(self, profile_id: UUID) -> list[CustomerSuccessHistory]:
        statement = (
            select(CustomerSuccessHistory)
            .where(
                CustomerSuccessHistory.profile_id == profile_id,
                CustomerSuccessHistory.tenant_id == self.tenant_id,
            )
            .order_by(
                CustomerSuccessHistory.created_at.desc(),
                CustomerSuccessHistory.id.desc(),
            )
        )
        return list(self.db.scalars(statement).all())

    def add_history(self, event: CustomerSuccessHistory) -> None:
        self.db.add(event)
        self.db.flush()
