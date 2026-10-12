from uuid import UUID

from sqlalchemy.orm import Session

from app.models.aml_rule import AMLRule
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import AMLRuleStatus, AMLRuleType


class AMLRuleRepository(TenantScopedRepository[AMLRule]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for AML rules.")

        super().__init__(db, AMLRule, resolved_tenant_id)

    def get_by_id(self, rule_id: UUID) -> AMLRule | None:
        return self.query().filter(AMLRule.id == rule_id).first()

    def get_all(self) -> list[AMLRule]:
        return self.query().order_by(AMLRule.name.asc()).all()

    def get_active_by_type(self, rule_type: AMLRuleType) -> list[AMLRule]:
        return (
            self.query()
            .filter(
                AMLRule.rule_type == rule_type,
                AMLRule.status == AMLRuleStatus.ACTIVE,
            )
            .order_by(AMLRule.name.asc())
            .all()
        )
