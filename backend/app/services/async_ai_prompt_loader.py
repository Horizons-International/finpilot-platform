"""Load active tenant-assigned prompts using native async database I/O."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.utils.enums import AIFunction, AIPromptStatus
from app.utils.errors import not_found


class AsyncAIPromptLoader:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "AI prompt tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    async def get_prompt(self, ai_function: AIFunction) -> AIPrompt:
        statement = (
            select(AIPrompt)
            .join(AIPromptAssignment, AIPromptAssignment.prompt_id == AIPrompt.id)
            .where(
                AIPromptAssignment.tenant_id == self.tenant_id,
                AIPromptAssignment.ai_function == ai_function,
                AIPrompt.tenant_id == self.tenant_id,
                AIPrompt.status == AIPromptStatus.ACTIVE,
            )
        )
        prompt = await self.db.scalar(statement)
        if prompt is None:
            raise not_found("Active AI prompt assignment")
        return prompt
