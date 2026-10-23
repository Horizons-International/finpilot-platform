"""Persistence operations for the platform-level partner onboarding queue."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_key import APIKey
from app.models.organization import Organization
from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingAdministrator,
    PartnerOnboardingDocument,
    PartnerOnboardingHistory,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.utils.enums import PartnerOnboardingStatus


class PartnerOnboardingRepository:
    """Persistence operations for pre-tenant onboarding and activation records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, onboarding: PartnerOnboarding) -> PartnerOnboarding:
        self.db.add(onboarding)
        self.db.flush()
        return onboarding

    def has_open_request_for_email(
        self,
        email: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        statement = select(PartnerOnboarding.id).where(
            PartnerOnboarding.contact_email == email,
            PartnerOnboarding.status != PartnerOnboardingStatus.REJECTED,
        )
        if exclude_id is not None:
            statement = statement.where(PartnerOnboarding.id != exclude_id)
        return self.db.scalar(statement) is not None

    def get_platform_admin(self, user_id: UUID) -> User | None:
        statement = (
            select(User)
            .where(User.id == user_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform administrator validates a reviewer for global "
                    "partner onboarding"
                ),
            )
        )
        return self.db.scalar(statement)

    def get_existing_user_id_by_email(self, email: str) -> UUID | None:
        """Check globally unique user email before onboarding activation."""
        statement = (
            select(User.id)
            .where(User.email == email)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "check globally unique user email before onboarding activation"
                ),
            )
        )
        return self.db.scalar(statement)

    def create_tenant(self, tenant: Tenant) -> Tenant:
        self.db.add(tenant)
        self.db.flush()
        return tenant

    def create_organization(self, organization: Organization) -> Organization:
        self.db.add(organization)
        self.db.flush()
        return organization

    def create_administrator(
        self, administrator: PartnerOnboardingAdministrator
    ) -> PartnerOnboardingAdministrator:
        self.db.add(administrator)
        self.db.flush()
        return administrator

    def create_document(
        self, document: PartnerOnboardingDocument
    ) -> PartnerOnboardingDocument:
        self.db.add(document)
        self.db.flush()
        return document

    def create_invitation(self, invitation: UserInvitation) -> UserInvitation:
        self.db.add(invitation)
        self.db.flush()
        return invitation

    def create_api_key(self, api_key: APIKey) -> APIKey:
        self.db.add(api_key)
        self.db.flush()
        return api_key

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

    def get_document(
        self,
        onboarding_id: UUID,
        document_id: UUID,
    ) -> PartnerOnboardingDocument | None:
        statement = select(PartnerOnboardingDocument).where(
            PartnerOnboardingDocument.onboarding_id == onboarding_id,
            PartnerOnboardingDocument.id == document_id,
        )
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
