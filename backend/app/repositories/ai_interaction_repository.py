from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ai_interaction import AIInteraction
from app.models.ai_prompt import AIPrompt
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import AIFunction


class AIInteractionRepository(TenantScopedRepository[AIInteraction]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for AI interactions.")

        super().__init__(db, AIInteraction, resolved_tenant_id)

    def _validate_related_records(self, interaction: AIInteraction) -> None:
        user_exists = (
            self.db.query(User.id)
            .filter(
                User.id == interaction.user_id,
                User.tenant_id == self.tenant_id,
            )
            .first()
        )
        if user_exists is None:
            raise ValueError("The AI interaction user does not belong to this tenant.")

        prompt_exists = (
            self.db.query(AIPrompt.id)
            .filter(
                AIPrompt.id == interaction.prompt_id,
                AIPrompt.tenant_id == self.tenant_id,
            )
            .first()
        )
        if prompt_exists is None:
            raise ValueError("The AI prompt does not belong to this tenant.")

    def create(self, interaction: AIInteraction) -> AIInteraction:
        self._validate_related_records(interaction)
        return super().create(interaction)

    def update(self, interaction: AIInteraction) -> AIInteraction:
        self._validate_related_records(interaction)
        return super().update(interaction)

    def get_by_id(
        self,
        interaction_id: UUID,
    ) -> AIInteraction | None:
        return self.query().filter(AIInteraction.id == interaction_id).first()

    def get_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
    ) -> list[AIInteraction]:
        return (
            self.query()
            .filter(AIInteraction.user_id == user_id)
            .order_by(AIInteraction.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_function(
        self,
        ai_function: AIFunction,
        *,
        limit: int = 50,
    ) -> list[AIInteraction]:
        return (
            self.query()
            .filter(AIInteraction.ai_function == ai_function)
            .order_by(AIInteraction.created_at.desc())
            .limit(limit)
            .all()
        )
