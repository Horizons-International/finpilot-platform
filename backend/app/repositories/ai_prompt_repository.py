from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPrompt
from app.repositories.base_repository import BaseRepository
from app.utils.enums import AIPromptStatus


class AIPromptRepository(BaseRepository[AIPrompt]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, AIPrompt)

    def get_lastest_by_name(
        self,
        name: str,
    ) -> AIPrompt | None:
        return (
            self.db.query(AIPrompt)
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
            self.db.query(AIPrompt)
            .filter(
                and_(
                    AIPrompt.name == name,
                    AIPrompt.version == version,
                )
            )
            .first()
        )

    def get_active(
        self,
        name: str,
    ) -> AIPrompt | None:
        return (
            self.db.query(AIPrompt)
            .filter(
                and_(
                    AIPrompt.name == name,
                    AIPrompt.status == AIPromptStatus.ACTIVE,
                )
            )
            .first()
        )

    def get_all_versions(
        self,
        name: str,
    ) -> list[AIPrompt]:
        return (
            self.db.query(AIPrompt)
            .filter(AIPrompt.name == name)
            .order_by(AIPrompt.version.desc())
            .all()
        )

    def get_all_active(self) -> list[AIPrompt]:
        return (
            self.db.query(AIPrompt)
            .filter(AIPrompt.status == AIPromptStatus.ACTIVE)
            .order_by(AIPrompt.name)
            .all()
        )
