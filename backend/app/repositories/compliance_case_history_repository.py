from uuid import UUID

from sqlalchemy.orm import Session

from app.models.compliance_case import ComplianceCase
from app.models.compliance_case_history import ComplianceCaseHistory
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class ComplianceCaseHistoryRepository(TenantScopedRepository[ComplianceCaseHistory]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError(
                "A tenant context is required for compliance case history."
            )

        super().__init__(db, ComplianceCaseHistory, resolved_tenant_id)

    def _validate_related_records(self, history: ComplianceCaseHistory) -> None:
        case_exists = (
            self.db.query(ComplianceCase.id)
            .filter(
                ComplianceCase.id == history.compliance_case_id,
                ComplianceCase.tenant_id == self.tenant_id,
            )
            .first()
        )
        if case_exists is None:
            raise ValueError("The compliance case does not belong to this tenant.")

        user_exists = (
            self.db.query(User.id)
            .filter(
                User.id == history.changed_by,
                User.tenant_id == self.tenant_id,
            )
            .first()
        )
        if user_exists is None:
            raise ValueError("The user does not belong to this tenant.")

    def create(self, history: ComplianceCaseHistory) -> ComplianceCaseHistory:
        self._validate_related_records(history)
        return super().create(history)

    def update(self, history: ComplianceCaseHistory) -> ComplianceCaseHistory:
        self._validate_related_records(history)
        return super().update(history)

    def get_by_case_id(
        self,
        compliance_case_id: UUID,
    ) -> list[ComplianceCaseHistory]:
        return (
            self.query()
            .filter(ComplianceCaseHistory.compliance_case_id == compliance_case_id)
            .order_by(ComplianceCaseHistory.created_at.asc())
            .all()
        )
