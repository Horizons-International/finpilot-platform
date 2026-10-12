from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPrompt
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import AIPromptStatus


class AIPromptRepository(TenantScopedRepository[AIPrompt]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for AI prompts.")

        super().__init__(db, AIPrompt, resolved_tenant_id)

    def _ensure_creator_belongs_to_tenant(self, user_id: UUID) -> None:
        user_exists = (
            self.db.query(User.id)
            .filter(
                User.id == user_id,
                User.tenant_id == self.tenant_id,
            )
            .first()
        )
        if user_exists is None:
            raise ValueError("The AI prompt creator does not belong to this tenant.")

    def create(self, prompt: AIPrompt) -> AIPrompt:
        self._ensure_creator_belongs_to_tenant(prompt.created_by)
        return super().create(prompt)

    def update(self, prompt: AIPrompt) -> AIPrompt:
        self._ensure_creator_belongs_to_tenant(prompt.created_by)
        return super().update(prompt)

    def get_lastest_by_name(self, name: str) -> AIPrompt | None:
        return (
            self.query()
            .filter(AIPrompt.name == name)
            .order_by(AIPrompt.version.desc())
            .first()
        )

    def get_by_name_and_version(
        self,
        name: str,
        version: int,
    ) -> AIPrompt | None:
        return (
            self.query()
            .filter(
                and_(
                    AIPrompt.name == name,
                    AIPrompt.version == version,
                )
            )
            .first()
        )

    def get_active(self, name: str) -> AIPrompt | None:
        return (
            self.query()
            .filter(
                and_(
                    AIPrompt.name == name,
                    AIPrompt.status == AIPromptStatus.ACTIVE,
                )
            )
            .first()
        )

    def get_all_versions(self, name: str) -> list[AIPrompt]:
        return (
            self.query()
            .filter(AIPrompt.name == name)
            .order_by(AIPrompt.version.desc())
            .all()
        )

    def get_all_active(self) -> list[AIPrompt]:
        return (
            self.query()
            .filter(AIPrompt.status == AIPromptStatus.ACTIVE)
            .order_by(AIPrompt.name)
            .all()
        )
