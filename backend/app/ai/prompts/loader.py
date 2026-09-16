from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPrompt
from app.repositories.ai_prompt_assignment_repository import (
    AIPromptAssignmentRepository,
)
from app.repositories.ai_prompt_repository import AIPromptRepository
from app.utils.enums import AIFunction, AIPromptStatus
from app.utils.errors import not_found


class AIPromptLoader:
    """
    Loads the active prompt assigned to an AI function.

    AI consumers should use this class instead of querying the
    ai_prompts table directly.
    """

    def __init__(self, db: Session) -> None:
        self.prompt_repository = AIPromptRepository(db)
        self.assignment_repository = AIPromptAssignmentRepository(db)

    def get_prompt(
        self,
        ai_function: AIFunction,
    ) -> AIPrompt:
        assignment = self.assignment_repository.get_by_function(ai_function)

        if assignment is None:
            raise not_found("AI prompt assignment")

        prompt = self.prompt_repository.get_by_id(assignment.prompt_id)

        if prompt is None:
            raise not_found("AI prompt")

        if prompt.status != AIPromptStatus.ACTIVE:
            raise not_found("Active AI prompt")

        return prompt

    def get_prompt_text(
        self,
        ai_function: AIFunction,
    ) -> str:
        prompt = self.get_prompt(ai_function)

        return prompt.prompt_text
