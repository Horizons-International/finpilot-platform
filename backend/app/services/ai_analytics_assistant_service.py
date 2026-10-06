from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
)
from app.ai.prompts.analytics import build_analytics_prompt
from app.ai.prompts.loader import AIPromptLoader
from app.ai.providers.factory import get_ai_provider
from app.ai.schemas.requests import (
    AIRequest,
    AIRequestType,
)
from app.ai.services.ai_service import AIService
from app.analytics.services.analytics_assistant_data_service import (
    AnalyticsAssistantDataService,
)
from app.models.ai_interaction import AIInteraction
from app.rag.retrieval import RetrievalService
from app.repositories.ai_interaction_repository import (
    AIInteractionRepository,
)
from app.schemas.ai_analytics_assistant import (
    AIAnalyticsModelResult,
    AIAnalyticsResponse,
    AIAnalyticsResult,
)
from app.services.ai_usage_service import AIUsageService
from app.utils.date_time import utc_now
from app.utils.enums import (
    AIFunction,
    AIInteractionStatus,
    AIResourceType,
)


class AIAnalyticsAssistantService:
    def __init__(
        self,
        db: Session,
        retrieval_service: RetrievalService | None = None,
        ai_service: AIService | None = None,
    ) -> None:
        self.db = db
        self.data_service = AnalyticsAssistantDataService(
            db,
        )
        self.interaction_repository = AIInteractionRepository(
            db,
        )
        self.prompt_loader = AIPromptLoader(
            db,
        )
        self.usage_service = AIUsageService(
            db,
        )

        self.ai_service = (
            ai_service
            if ai_service is not None
            else AIService(
                provider=get_ai_provider(),
            )
        )

        self.retrieval_service = retrieval_service

    @staticmethod
    def _get_ai_provider():
        from app.ai.providers.factory import get_ai_provider

        return get_ai_provider()

    def ask(
        self,
        *,
        question: str,
        user_id: UUID,
        retrieval_limit: int = 5,
    ) -> AIAnalyticsResponse:
        from app.analytics.assistant.question_router import (
            resolve_analytics_question,
        )

        plan = resolve_analytics_question(
            question,
        )

        data_bundle = self.data_service.get_data(
            plan,
        )

        context = dict(
            data_bundle.context,
        )

        context["knowledge_base"] = self._retrieve_knowledge(
            question=question,
            retrieval_limit=retrieval_limit,
        )

        prompt = self.prompt_loader.get_prompt(
            AIFunction.ANALYTICS_ASSISTANT,
        )

        full_prompt = build_analytics_prompt(
            system_prompt=prompt.prompt_text,
            question=question,
            context=context,
        )

        analytics_request_id = uuid4()

        interaction = AIInteraction(
            user_id=user_id,
            ai_function=AIFunction.ANALYTICS_ASSISTANT,
            prompt_id=prompt.id,
            resource_type=AIResourceType.ANALYTICS,
            resource_id=analytics_request_id,
            question=question,
            context=context,
            status=AIInteractionStatus.PENDING,
        )

        interaction = self.interaction_repository.create(
            interaction,
        )

        self.db.commit()
        self.db.refresh(interaction)

        ai_request = AIRequest(
            request_type=AIRequestType.ANALYTICS_ASSISTANT,
            prompt=full_prompt,
            structured=True,
        )

        started_at = monotonic()

        try:
            response = self.ai_service.generate(
                ai_request,
            )

            response_time = int(
                (monotonic() - started_at) * 1000,
            )

            if response.structured_data is None:
                raise AIProviderError(
                    "AI provider did not return structured analytics data.",
                )

            model_result = AIAnalyticsModelResult.model_validate(
                response.structured_data,
            )

            result = AIAnalyticsResult(
                summary=model_result.summary,
                supporting_data=data_bundle.supporting_data,
                suggested_insights=model_result.suggested_insights,
                confidence=model_result.confidence,
            )

            interaction.status = AIInteractionStatus.COMPLETED
            interaction.response_text = response.content
            interaction.response_data = result.model_dump(
                mode="json",
            )
            interaction.provider_name = response.provider_name
            interaction.model = self._get_model_name()
            interaction.provider_request_id = (
                str(response.request_id) if response.request_id else None
            )
            interaction.completed_at = utc_now()

            self.interaction_repository.update(
                interaction,
            )

            self.db.commit()
            self.db.refresh(interaction)

            self.usage_service.record(
                user_id=user_id,
                feature=AIFunction.ANALYTICS_ASSISTANT.value,
                model=interaction.model or "",
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                response_time=response_time,
            )

            return AIAnalyticsResponse(
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
            response_time = int(
                (monotonic() - started_at) * 1000,
            )

            self.db.rollback()

            failed_interaction = self.interaction_repository.get_by_id(
                interaction.id,
            )

            if failed_interaction is not None:
                failed_interaction.status = AIInteractionStatus.FAILED
                failed_interaction.error_message = str(
                    exc,
                )
                failed_interaction.completed_at = utc_now()

                self.interaction_repository.update(
                    failed_interaction,
                )

                self.db.commit()

            self.usage_service.record(
                user_id=user_id,
                feature=AIFunction.ANALYTICS_ASSISTANT.value,
                model=self._get_model_name() or "",
                input_tokens=0,
                output_tokens=0,
                response_time=response_time,
                error_message=str(exc),
            )

            raise

    def _retrieve_knowledge(
        self,
        *,
        question: str,
        retrieval_limit: int,
    ) -> dict:
        if self.retrieval_service is None:
            return {
                "query": question,
                "results": [],
            }

        try:
            results = self.retrieval_service.retrieve(
                query=question,
                limit=retrieval_limit,
            )

        except (
            AIConfigurationError,
            AIProviderError,
            SQLAlchemyError,
        ):
            # RAG is supplemental for analytics. A missing vector
            # store or embedding provider must not prevent a business
            # analytics question from being answered.
            return {
                "query": question,
                "results": [],
            }

        return {
            "query": question,
            "results": [
                result.model_dump(
                    mode="json",
                )
                for result in results
            ],
        }

    @staticmethod
    def _get_model_name() -> str | None:
        from app.core.config import settings

        return settings.AI_MODEL
