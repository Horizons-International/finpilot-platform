from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import AIFunction


class AIPromptAssignmentRepository(TenantScopedRepository[AIPromptAssignment]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for AI prompt assignments.")

        super().__init__(db, AIPromptAssignment, resolved_tenant_id)

    def _ensure_prompt_belongs_to_tenant(self, prompt_id: UUID) -> None:
        prompt_exists = (
            self.db.query(AIPrompt.id)
            .filter(
                AIPrompt.id == prompt_id,
                AIPrompt.tenant_id == self.tenant_id,
            )
            .first()
        )
        if prompt_exists is None:
            raise ValueError("The AI prompt does not belong to the current tenant.")

    def create(self, assignment: AIPromptAssignment) -> AIPromptAssignment:
        self._ensure_prompt_belongs_to_tenant(assignment.prompt_id)
        return super().create(assignment)

    def update(self, assignment: AIPromptAssignment) -> AIPromptAssignment:
        self._ensure_prompt_belongs_to_tenant(assignment.prompt_id)
        return super().update(assignment)

    def get_by_function(
        self,
        ai_function: AIFunction,
    ) -> AIPromptAssignment | None:
        return (
            self.query().filter(AIPromptAssignment.ai_function == ai_function).first()
        )

    def get_by_prompt_id(
        self,
        prompt_id: UUID,
    ) -> list[AIPromptAssignment]:
        return self.query().filter(AIPromptAssignment.prompt_id == prompt_id).all()

    def get_all(self) -> list[AIPromptAssignment]:
        return self.query().order_by(AIPromptAssignment.ai_function).all()
