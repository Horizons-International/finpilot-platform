from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.prompts.compliance import build_compliance_prompt
from app.ai.prompts.loader import AIPromptLoader
from app.ai.providers.factory import get_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.ai_service import AIService
from app.models.ai_interaction import AIInteraction
from app.repositories.ai_interaction_repository import (
    AIInteractionRepository,
)
from app.schemas.ai_assistant import (
    AIComplianceRequest,
    AIComplianceResponse,
    AIComplianceResult,
)
from app.services.compliance_context_service import (
    ComplianceContextService,
)
from app.utils.date_time import utc_now
from app.utils.enums import AIInteractionStatus
from app.utils.errors import bad_request, not_found


class AIComplianceService:
    def __init__(self, db: Session) -> None:
        self.db = db

        self.interaction_repository = AIInteractionRepository(db)
        self.context_service = ComplianceContextService(db)
        self.prompt_loader = AIPromptLoader(db)

        self.ai_service = AIService(
            provider=get_ai_provider(),
        )

    def ask(
        self,
        request: AIComplianceRequest,
        *,
        user_id: UUID,
    ) -> AIComplianceResponse:
        context, resource_type, resource_id = self.context_service.build_context(
            request.ai_function,
            customer_id=request.customer_id,
            verification_case_id=request.verification_case_id,
            document_id=request.document_id,
        )

        prompt = self.prompt_loader.get_prompt(
            request.ai_function,
        )

        full_prompt = build_compliance_prompt(
            system_prompt=prompt.prompt_text,
            question=request.question,
            context=context,
        )

        interaction = AIInteraction(
            user_id=user_id,
            ai_function=request.ai_function,
            prompt_id=prompt.id,
            resource_type=resource_type,
            resource_id=resource_id,
            question=request.question,
            context=context,
            status=AIInteractionStatus.PENDING,
        )

        interaction = self.interaction_repository.create(interaction)

        self.db.commit()
        self.db.refresh(interaction)

        ai_request = AIRequest(
            request_type=AIRequestType.COMPLIANCE_ASSISTANT,
            prompt=full_prompt,
            customer_id=request.customer_id,
            document_id=request.document_id,
            structured=True,
        )

        try:
            response = self.ai_service.generate(ai_request)

            if response.structured_data is None:
                raise bad_request("AI provider did not return structured data.")

            interaction.status = AIInteractionStatus.COMPLETED
            interaction.response_text = response.content
            interaction.response_data = response.structured_data
            interaction.provider_name = response.provider_name
            interaction.model = self._get_model_name()
            interaction.provider_request_id = (
                str(response.request_id) if response.request_id else None
            )
            interaction.completed_at = utc_now()

            self.interaction_repository.update(interaction)

            self.db.commit()
            self.db.refresh(interaction)

            result = AIComplianceResult(
                **response.structured_data,
            )

            return AIComplianceResponse(
                interaction_id=interaction.id,
                ai_function=interaction.ai_function,
                prompt_id=interaction.prompt_id,
                status=interaction.status,
                provider_name=response.provider_name,
                model=interaction.model,
                content=response.content,
                result=result,
            )

        except Exception as exc:
            self.db.rollback()

            failed_interaction = self.interaction_repository.get_by_id(interaction.id)

            if failed_interaction is not None:
                failed_interaction.status = AIInteractionStatus.FAILED
                failed_interaction.error_message = str(exc)
                failed_interaction.completed_at = utc_now()

                self.interaction_repository.update(failed_interaction)

                self.db.commit()

            raise

    def get_interaction(
        self,
        interaction_id: UUID,
        *,
        user_id: UUID,
    ) -> AIInteraction:
        interaction = self.interaction_repository.get_by_id(interaction_id)

        if interaction is None:
            raise not_found("AI interaction")

        if interaction.user_id != user_id:
            raise bad_request("You do not have access to this AI interaction.")

        return interaction

    def get_user_interactions(
        self,
        *,
        user_id: UUID,
    ) -> list[AIInteraction]:
        return self.interaction_repository.get_for_user(
            user_id,
        )

    @staticmethod
    def _get_model_name() -> str | None:
        from app.core.config import settings

        return settings.AI_MODEL
