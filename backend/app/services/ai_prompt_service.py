from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.repositories.ai_prompt_assignment_repository import (
    AIPromptAssignmentRepository,
)
from app.repositories.ai_prompt_repository import AIPromptRepository
from app.schemas.ai_prompt import (
    AIPromptAssignmentCreate,
    AIPromptCreate,
    AIPromptStatusUpdate,
    AIPromptVersionCreate,
)
from app.services.audit_service import AuditService
from app.utils.enums import AIFunction, AIPromptStatus, AuditEventType
from app.utils.errors import bad_request, not_found


class AIPromptService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AIPromptRepository(db)
        self.assignment_repository = AIPromptAssignmentRepository(db)
        self.audit_service = AuditService(db)

    def get_all(self) -> list[AIPrompt]:
        return self.repository.get_all()

    def get_all_active(self) -> list[AIPrompt]:
        return self.repository.get_all_active()

    def get_by_id(
        self,
        prompt_id: UUID,
    ) -> AIPrompt:
        prompt = self.repository.get_by_id(prompt_id)

        if prompt is None:
            raise not_found("AI prompt")

        return prompt

    def get_versions(
        self,
        name: str,
    ) -> list[AIPrompt]:
        prompts = self.repository.get_all_versions(name)

        if not prompts:
            raise not_found("AI prompt")

        return prompts

    def get_active(
        self,
        name: str,
    ) -> AIPrompt:
        prompt = self.repository.get_active(name)

        if prompt is None:
            raise not_found("Active AI prompt")

        return prompt

    def create(
        self,
        data: AIPromptCreate,
        user_id: UUID,
        email: str,
    ) -> AIPrompt:
        existing = self.repository.get_lastest_by_name(data.name)

        if existing is not None:
            raise bad_request(
                "An AI prompt with this name already exists. "
                "Create a new version instead."
            )

        prompt = AIPrompt(
            name=data.name,
            purpose=data.purpose,
            prompt_text=data.prompt_text,
            version=1,
            status=AIPromptStatus.INACTIVE,
            created_by=user_id,
        )

        try:
            prompt = self.repository.create(prompt)

            self.audit_service.log_event(
                event_type=AuditEventType.AI_PROMPT_CREATED,
                user_id=user_id,
                email=email,
                resource_type="ai_prompt",
                resource_id=prompt.id,
            )

            self.db.commit()
            self.db.refresh(prompt)

            return prompt

        except IntegrityError as exc:
            self.db.rollback()
            raise bad_request("An AI prompt with this name already exists.") from exc

    def create_version(
        self,
        prompt_id: UUID,
        data: AIPromptVersionCreate,
        user_id: UUID,
        email: str,
    ) -> AIPrompt:
        current_prompt = self.get_by_id(prompt_id)

        latest_prompt = self.repository.get_lastest_by_name(current_prompt.name)

        if latest_prompt is None:
            raise not_found("AI prompt")

        new_version = latest_prompt.version + 1

        prompt = AIPrompt(
            name=current_prompt.name,
            purpose=current_prompt.purpose,
            prompt_text=data.prompt_text,
            version=new_version,
            status=AIPromptStatus.INACTIVE,
            created_by=user_id,
        )

        try:
            prompt = self.repository.create(prompt)

            self.audit_service.log_event(
                event_type=AuditEventType.AI_PROMPT_VERSION_CREATED,
                user_id=user_id,
                email=email,
                resource_type="ai_prompt",
                resource_id=prompt.id,
            )

            self.db.commit()
            self.db.refresh(prompt)

            return prompt

        except IntegrityError as exc:
            self.db.rollback()
            raise bad_request("The AI prompt version could not be created.") from exc

    def update_status(
        self,
        prompt_id: UUID,
        data: AIPromptStatusUpdate,
        user_id: UUID,
        email: str,
    ) -> AIPrompt:
        prompt = self.get_by_id(prompt_id)

        if prompt.status == data.status:
            raise bad_request(f"AI prompt is already {data.status.value.lower()}.")

        if data.status == AIPromptStatus.ACTIVE:
            return self._activate(
                prompt=prompt,
                user_id=user_id,
                email=email,
            )

        return self._deactivate(
            prompt=prompt,
            user_id=user_id,
            email=email,
        )

    def _activate(
        self,
        prompt: AIPrompt,
        user_id: UUID,
        email: str,
    ) -> AIPrompt:
        existing_active = self.repository.get_active(prompt.name)

        if existing_active is not None and existing_active.id != prompt.id:
            raise bad_request(
                "Another version of this AI prompt is already active. "
                "Deactivate it before activating this version."
            )

        prompt.status = AIPromptStatus.ACTIVE

        self.repository.update(prompt)

        self.audit_service.log_event(
            event_type=AuditEventType.AI_PROMPT_ACTIVATED,
            user_id=user_id,
            email=email,
            resource_type="ai_prompt",
            resource_id=prompt.id,
        )

        try:
            self.db.commit()
            self.db.refresh(prompt)

            return prompt

        except IntegrityError as exc:
            self.db.rollback()
            raise bad_request("The AI prompt could not be activated.") from exc

    def _deactivate(
        self,
        prompt: AIPrompt,
        user_id: UUID,
        email: str,
    ) -> AIPrompt:
        prompt.status = AIPromptStatus.INACTIVE

        self.repository.update(prompt)

        self.audit_service.log_event(
            event_type=AuditEventType.AI_PROMPT_DEACTIVATED,
            user_id=user_id,
            email=email,
            resource_type="ai_prompt",
            resource_id=prompt.id,
        )

        self.db.commit()
        self.db.refresh(prompt)

        return prompt

    def assign(
        self,
        data: AIPromptAssignmentCreate,
        user_id: UUID,
        email: str,
    ) -> AIPromptAssignment:
        prompt = self.get_by_id(data.prompt_id)

        if prompt.status != AIPromptStatus.ACTIVE:
            raise bad_request("Only an active AI prompt can be assigned.")

        existing = self.assignment_repository.get_by_function(data.ai_function)

        if existing is None:
            assignment = AIPromptAssignment(
                ai_function=data.ai_function,
                prompt_id=prompt.id,
            )

            assignment = self.assignment_repository.create(assignment)

        else:
            existing.prompt_id = prompt.id

            assignment = self.assignment_repository.update(existing)

        self.audit_service.log_event(
            event_type=AuditEventType.AI_PROMPT_ASSIGNED,
            user_id=user_id,
            email=email,
            resource_type="ai_prompt",
            resource_id=prompt.id,
        )

        self.db.commit()
        self.db.refresh(assignment)

        return assignment

    def get_assignment(
        self,
        ai_function: AIFunction,
    ) -> AIPromptAssignment:
        assignment = self.assignment_repository.get_by_function(ai_function)

        if assignment is None:
            raise not_found("AI prompt assignment")

        prompt = self.repository.get_by_id(assignment.prompt_id)

        if prompt is None:
            raise not_found("AI prompt")

        if prompt.status != AIPromptStatus.ACTIVE:
            raise bad_request("The assigned AI prompt is not active.")

        return assignment

    def get_prompt_for_function(
        self,
        ai_function: AIFunction,
    ) -> AIPrompt:
        assignment = self.assignment_repository.get_by_function(ai_function)

        if assignment is None:
            raise not_found("AI prompt assignment")

        prompt = self.repository.get_by_id(assignment.prompt_id)

        if prompt is None:
            raise not_found("AI prompt")

        if prompt.status != AIPromptStatus.ACTIVE:
            raise not_found("Active AI prompt")

        return prompt

    def get_all_assignments(self) -> list[AIPromptAssignment]:
        return self.assignment_repository.get_all()
