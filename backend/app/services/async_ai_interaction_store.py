"""Tenant-validated persistence helpers for AI assistant interactions."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_interaction import AIInteraction
from app.models.ai_prompt import AIPrompt
from app.models.user import User
from app.utils.date_time import utc_now
from app.utils.enums import AIFunction, AIInteractionStatus, AIResourceType


class AsyncAIInteractionStore:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "AI interaction tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    async def create_pending(
        self,
        *,
        user_id: UUID,
        ai_function: AIFunction,
        prompt_id: UUID,
        resource_type: AIResourceType,
        resource_id: UUID,
        question: str,
        context: dict[str, Any],
    ) -> AIInteraction:
        user_exists = await self.db.scalar(
            select(User.id).where(
                User.id == user_id,
                User.tenant_id == self.tenant_id,
            )
        )
        if user_exists is None:
            raise ValueError("The AI interaction user does not belong to this tenant.")
        prompt_exists = await self.db.scalar(
            select(AIPrompt.id).where(
                AIPrompt.id == prompt_id,
                AIPrompt.tenant_id == self.tenant_id,
            )
        )
        if prompt_exists is None:
            raise ValueError("The AI prompt does not belong to this tenant.")
        interaction = AIInteraction(
            tenant_id=self.tenant_id,
            user_id=user_id,
            ai_function=ai_function,
            prompt_id=prompt_id,
            resource_type=resource_type,
            resource_id=resource_id,
            question=question,
            context=context,
            status=AIInteractionStatus.PENDING,
        )
        self.db.add(interaction)
        await self.db.commit()
        await self.db.refresh(interaction)
        return interaction

    async def mark_completed(
        self,
        interaction: AIInteraction,
        *,
        response_text: str,
        response_data: dict[str, Any],
        provider_name: str,
        model: str | None,
        provider_request_id: str | None,
    ) -> AIInteraction:
        interaction.status = AIInteractionStatus.COMPLETED
        interaction.response_text = response_text
        interaction.response_data = response_data
        interaction.provider_name = provider_name
        interaction.model = model
        interaction.provider_request_id = provider_request_id
        interaction.completed_at = utc_now()
        await self.db.commit()
        await self.db.refresh(interaction)
        return interaction

    async def mark_failed(self, interaction_id: UUID, error_message: str) -> None:
        await self.db.rollback()
        interaction = await self.db.scalar(
            select(AIInteraction).where(
                AIInteraction.id == interaction_id,
                AIInteraction.tenant_id == self.tenant_id,
            )
        )
        if interaction is None:
            return
        interaction.status = AIInteractionStatus.FAILED
        interaction.error_message = error_message[:4000]
        interaction.completed_at = utc_now()
        await self.db.commit()
