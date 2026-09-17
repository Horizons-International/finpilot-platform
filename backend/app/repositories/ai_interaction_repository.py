from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ai_interaction import AIInteraction
from app.repositories.base_repository import BaseRepository
from app.utils.enums import AIFunction


class AIInteractionRepository(BaseRepository[AIInteraction]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, AIInteraction)

    def get_by_id(
        self,
        interaction_id: UUID,
    ) -> AIInteraction | None:
        return (
            self.db.query(AIInteraction)
            .filter(AIInteraction.id == interaction_id)
            .first()
        )

    def get_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
    ) -> list[AIInteraction]:
        return (
            self.db.query(AIInteraction)
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
            self.db.query(AIInteraction)
            .filter(AIInteraction.ai_function == ai_function)
            .order_by(AIInteraction.created_at.desc())
            .limit(limit)
            .all()
        )
