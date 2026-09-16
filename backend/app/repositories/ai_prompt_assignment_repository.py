from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ai_prompt_assignment import AIPromptAssignment
from app.repositories.base_repository import BaseRepository
from app.utils.enums import AIFunction


class AIPromptAssignmentRepository(BaseRepository[AIPromptAssignment]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, AIPromptAssignment)

    def get_by_function(
        self,
        ai_function: AIFunction,
    ) -> AIPromptAssignment | None:
        return (
            self.db.query(AIPromptAssignment)
            .filter(
                AIPromptAssignment.ai_function == ai_function,
            )
            .first()
        )

    def get_by_prompt_id(
        self,
        prompt_id: UUID,
    ) -> list[AIPromptAssignment]:
        return (
            self.db.query(AIPromptAssignment)
            .filter(
                AIPromptAssignment.prompt_id == prompt_id,
            )
            .all()
        )

    def get_all(
        self,
    ) -> list[AIPromptAssignment]:
        return (
            self.db.query(AIPromptAssignment)
            .order_by(AIPromptAssignment.ai_function)
            .all()
        )
