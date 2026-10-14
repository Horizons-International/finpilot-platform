"""Persistence operations for the platform-level partner onboarding queue."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingHistory,
)
from app.utils.enums import PartnerOnboardingStatus


class PartnerOnboardingRepository:
    """Repository for records managed only by platform administrators."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, onboarding: PartnerOnboarding) -> PartnerOnboarding:
        self.db.add(onboarding)
        self.db.flush()
        return onboarding

    def get_by_id(
        self,
        onboarding_id: UUID,
        *,
        for_update: bool = False,
    ) -> PartnerOnboarding | None:
        statement = select(PartnerOnboarding).where(
            PartnerOnboarding.id == onboarding_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def list_all(
        self,
        *,
        status: PartnerOnboardingStatus | None = None,
        assigned_to: UUID | None = None,
    ) -> list[PartnerOnboarding]:
        statement = select(PartnerOnboarding)
        if status is not None:
            statement = statement.where(PartnerOnboarding.status == status)
        if assigned_to is not None:
            statement = statement.where(PartnerOnboarding.assigned_to == assigned_to)
        return list(
            self.db.scalars(
                statement.order_by(PartnerOnboarding.created_at.desc())
            ).all()
        )

    def history(self, onboarding_id: UUID) -> list[PartnerOnboardingHistory]:
        statement = (
            select(PartnerOnboardingHistory)
            .where(PartnerOnboardingHistory.onboarding_id == onboarding_id)
            .order_by(
                PartnerOnboardingHistory.created_at.asc(),
                PartnerOnboardingHistory.id.asc(),
            )
        )
        return list(self.db.scalars(statement).all())

    def add_history(
        self,
        *,
        onboarding: PartnerOnboarding,
        action: str,
        previous_status: PartnerOnboardingStatus | None,
        changed_by: UUID | None,
        notes: str | None,
    ) -> PartnerOnboardingHistory:
        item = PartnerOnboardingHistory(
            onboarding_id=onboarding.id,
            action=action,
            previous_status=previous_status,
            status=onboarding.status,
            changed_by=changed_by,
            notes=notes,
        )
        self.db.add(item)
        self.db.flush()
        return item
