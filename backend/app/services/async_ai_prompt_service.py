"""Tenant-scoped async administration of versioned AI prompts."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.models.user import User
from app.schemas.ai_prompt import (
    AIPromptAssignmentCreate,
    AIPromptCreate,
    AIPromptStatusUpdate,
    AIPromptVersionCreate,
)
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import AIFunction, AIPromptStatus, AuditEventType
from app.utils.errors import bad_request, not_found


class AsyncAIPromptService:
    """Manage prompts while retaining the synchronous runtime service for AI calls."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "AI prompt tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.audit = AsyncAuditService(db)

    async def _validate_creator(self, user_id: UUID) -> None:
        creator_id = await self.db.scalar(
            select(User.id).where(User.id == user_id, User.tenant_id == self.tenant_id)
        )
        if creator_id is None:
            raise bad_request("The AI prompt creator does not belong to this tenant.")

    async def _get_prompt(self, prompt_id: UUID, *, lock: bool = False) -> AIPrompt:
        statement = select(AIPrompt).where(
            AIPrompt.id == prompt_id,
            AIPrompt.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        prompt = await self.db.scalar(statement)
        if prompt is None:
            raise not_found("AI prompt")
        return prompt

    async def get_all(self) -> list[AIPrompt]:
        result = await self.db.scalars(
            select(AIPrompt)
            .where(AIPrompt.tenant_id == self.tenant_id)
            .order_by(AIPrompt.name, AIPrompt.version.desc())
        )
        return list(result.all())

    async def get_all_active(self) -> list[AIPrompt]:
        result = await self.db.scalars(
            select(AIPrompt)
            .where(
                AIPrompt.tenant_id == self.tenant_id,
                AIPrompt.status == AIPromptStatus.ACTIVE,
            )
            .order_by(AIPrompt.name)
        )
        return list(result.all())

    async def get_by_id(self, prompt_id: UUID) -> AIPrompt:
        return await self._get_prompt(prompt_id)

    async def get_versions(self, name: str) -> list[AIPrompt]:
        result = await self.db.scalars(
            select(AIPrompt)
            .where(AIPrompt.tenant_id == self.tenant_id, AIPrompt.name == name)
            .order_by(AIPrompt.version.desc())
        )
        prompts = list(result.all())
        if not prompts:
            raise not_found("AI prompt")
        return prompts

    async def get_active(self, name: str) -> AIPrompt:
        prompt = await self.db.scalar(
            select(AIPrompt).where(
                AIPrompt.tenant_id == self.tenant_id,
                AIPrompt.name == name,
                AIPrompt.status == AIPromptStatus.ACTIVE,
            )
        )
        if prompt is None:
            raise not_found("Active AI prompt")
        return prompt

    async def create(
        self,
        *,
        data: AIPromptCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AIPrompt:
        name = data.name.strip()
        if not name:
            raise bad_request("AI prompt name is required.")
        if not data.purpose.strip():
            raise bad_request("AI prompt purpose is required.")
        if not data.prompt_text.strip():
            raise bad_request("AI prompt text is required.")
        await self._validate_creator(user_id)
        existing = await self.db.scalar(
            select(AIPrompt.id).where(
                AIPrompt.tenant_id == self.tenant_id, AIPrompt.name == name
            )
        )
        if existing is not None:
            raise bad_request(
                "An AI prompt with this name already exists. "
                "Create a new version instead."
            )
        prompt = AIPrompt(
            tenant_id=self.tenant_id,
            name=name,
            purpose=data.purpose.strip(),
            prompt_text=data.prompt_text,
            version=1,
            status=AIPromptStatus.INACTIVE,
            created_by=user_id,
        )
        self.db.add(prompt)
        try:
            await self.db.flush()
            await self.audit.log_event(
                event_type=AuditEventType.AI_PROMPT_CREATED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="ai_prompt",
                resource_id=prompt.id,
            )
            await self.db.commit()
            await self.db.refresh(prompt)
            return prompt
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request("An AI prompt with this name already exists.") from exc
        except Exception:
            await self.db.rollback()
            raise

    async def create_version(
        self,
        *,
        prompt_id: UUID,
        data: AIPromptVersionCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AIPrompt:
        current = await self._get_prompt(prompt_id, lock=True)
        await self._validate_creator(user_id)
        if not data.prompt_text.strip():
            raise bad_request("AI prompt text is required.")
        latest = await self.db.scalar(
            select(AIPrompt)
            .where(
                AIPrompt.tenant_id == self.tenant_id,
                AIPrompt.name == current.name,
            )
            .order_by(AIPrompt.version.desc())
            .limit(1)
            .with_for_update()
        )
        if latest is None:
            raise not_found("AI prompt")
        prompt = AIPrompt(
            tenant_id=self.tenant_id,
            name=current.name,
            purpose=current.purpose,
            prompt_text=data.prompt_text,
            version=latest.version + 1,
            status=AIPromptStatus.INACTIVE,
            created_by=user_id,
        )
        self.db.add(prompt)
        try:
            await self.db.flush()
            await self.audit.log_event(
                event_type=AuditEventType.AI_PROMPT_VERSION_CREATED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="ai_prompt",
                resource_id=prompt.id,
            )
            await self.db.commit()
            await self.db.refresh(prompt)
            return prompt
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request("The AI prompt version could not be created.") from exc
        except Exception:
            await self.db.rollback()
            raise

    async def update_status(
        self,
        *,
        prompt_id: UUID,
        data: AIPromptStatusUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AIPrompt:
        prompt = await self._get_prompt(prompt_id, lock=True)
        if prompt.status == data.status:
            raise bad_request(f"AI prompt is already {data.status.value.lower()}.")
        if data.status == AIPromptStatus.ACTIVE:
            existing = await self.db.scalar(
                select(AIPrompt)
                .where(
                    AIPrompt.tenant_id == self.tenant_id,
                    AIPrompt.name == prompt.name,
                    AIPrompt.status == AIPromptStatus.ACTIVE,
                )
                .with_for_update()
            )
            if existing is not None and existing.id != prompt.id:
                raise bad_request(
                    "Another version of this AI prompt is already active. "
                    "Deactivate it before activating this version."
                )
            event_type = AuditEventType.AI_PROMPT_ACTIVATED
        else:
            event_type = AuditEventType.AI_PROMPT_DEACTIVATED
        prompt.status = data.status
        try:
            await self.audit.log_event(
                event_type=event_type,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="ai_prompt",
                resource_id=prompt.id,
            )
            await self.db.commit()
            await self.db.refresh(prompt)
            return prompt
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request("The AI prompt could not be activated.") from exc
        except Exception:
            await self.db.rollback()
            raise

    async def assign(
        self,
        *,
        data: AIPromptAssignmentCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AIPromptAssignment:
        prompt = await self._get_prompt(data.prompt_id, lock=True)
        if prompt.status != AIPromptStatus.ACTIVE:
            raise bad_request("Only an active AI prompt can be assigned.")
        assignment = await self.db.scalar(
            select(AIPromptAssignment)
            .where(
                AIPromptAssignment.tenant_id == self.tenant_id,
                AIPromptAssignment.ai_function == data.ai_function,
            )
            .with_for_update()
        )
        if assignment is None:
            assignment = AIPromptAssignment(
                tenant_id=self.tenant_id,
                ai_function=data.ai_function,
                prompt_id=prompt.id,
            )
            self.db.add(assignment)
        else:
            assignment.prompt_id = prompt.id
        try:
            await self.audit.log_event(
                event_type=AuditEventType.AI_PROMPT_ASSIGNED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="ai_prompt",
                resource_id=prompt.id,
            )
            await self.db.commit()
            await self.db.refresh(assignment)
            return assignment
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request(
                "This AI function already has an assignment for this tenant."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def get_assignment(self, ai_function: AIFunction) -> AIPromptAssignment:
        assignment = await self.db.scalar(
            select(AIPromptAssignment).where(
                AIPromptAssignment.tenant_id == self.tenant_id,
                AIPromptAssignment.ai_function == ai_function,
            )
        )
        if assignment is None:
            raise not_found("AI prompt assignment")
        prompt = await self._get_prompt(assignment.prompt_id)
        if prompt.status != AIPromptStatus.ACTIVE:
            raise bad_request("The assigned AI prompt is not active.")
        return assignment

    async def get_all_assignments(self) -> list[AIPromptAssignment]:
        result = await self.db.scalars(
            select(AIPromptAssignment)
            .where(AIPromptAssignment.tenant_id == self.tenant_id)
            .order_by(AIPromptAssignment.ai_function)
        )
        return list(result.all())
