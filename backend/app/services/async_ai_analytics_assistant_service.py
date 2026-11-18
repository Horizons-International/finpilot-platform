"""Native-async analytics assistant orchestration."""

from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.prompts.analytics import build_analytics_prompt
from app.ai.providers.async_factory import get_async_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.async_ai_service import AsyncAIService
from app.analytics.assistant.question_router import resolve_analytics_question
from app.analytics.services.async_analytics_assistant_data_service import (
    AsyncAnalyticsAssistantDataService,
)
from app.core.config import settings
from app.rag.async_retrieval import AsyncRetrievalService
from app.schemas.ai_analytics_assistant import (
    AIAnalyticsModelResult,
    AIAnalyticsResponse,
    AIAnalyticsResult,
)
from app.services.async_ai_interaction_store import AsyncAIInteractionStore
from app.services.async_ai_prompt_loader import AsyncAIPromptLoader
from app.services.async_ai_usage_service import AsyncAIUsageService
from app.utils.enums import AIFunction, AIResourceType


class AsyncAIAnalyticsAssistantService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        retrieval_service: AsyncRetrievalService | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.data_service = AsyncAnalyticsAssistantDataService(db, tenant_id)
        self.prompt_loader = AsyncAIPromptLoader(db, tenant_id)
        self.interactions = AsyncAIInteractionStore(db, tenant_id)
        self.usage = AsyncAIUsageService(db, tenant_id)
        self.retrieval_service = retrieval_service

    async def _retrieve_knowledge(self, question: str, limit: int) -> dict[str, Any]:
        empty: dict[str, Any] = {"query": question, "results": []}
        if self.retrieval_service is None:
            return empty
        try:
            results = await self.retrieval_service.retrieve(query=question, limit=limit)
        except (AIConfigurationError, AIProviderError, SQLAlchemyError):
            # RAG enrichment is supplemental for analytics and must not hide
            # the tenant's authoritative structured analytics evidence.
            return empty
        return {
            "query": question,
            "results": [item.model_dump(mode="json") for item in results],
        }

    async def ask(
        self,
        *,
        question: str,
        user_id: UUID,
        retrieval_limit: int = 5,
    ) -> AIAnalyticsResponse:
        plan = resolve_analytics_question(question)
        data = await self.data_service.get_data(plan)
        context = dict(data.context)
        context["knowledge_base"] = await self._retrieve_knowledge(
            question, retrieval_limit
        )
        prompt_record = await self.prompt_loader.get_prompt(
            AIFunction.ANALYTICS_ASSISTANT
        )
        full_prompt = build_analytics_prompt(
            system_prompt=prompt_record.prompt_text,
            question=question,
            context=context,
        )
        interaction = await self.interactions.create_pending(
            user_id=user_id,
            ai_function=AIFunction.ANALYTICS_ASSISTANT,
            prompt_id=prompt_record.id,
            resource_type=AIResourceType.ANALYTICS,
            resource_id=uuid4(),
            question=question,
            context=context,
        )
        started = monotonic()
        try:
            async with AsyncAIService(provider=get_async_ai_provider()) as ai:
                response = await ai.generate(
                    AIRequest(
                        request_type=AIRequestType.ANALYTICS_ASSISTANT,
                        prompt=full_prompt,
                        structured=True,
                    )
                )
            elapsed = int((monotonic() - started) * 1000)
            if response.structured_data is None:
                raise AIProviderError(
                    "AI provider did not return structured analytics data."
                )
            model_result = AIAnalyticsModelResult.model_validate(
                response.structured_data
            )
            result = AIAnalyticsResult(
                summary=model_result.summary,
                supporting_data=data.supporting_data,
                suggested_insights=model_result.suggested_insights,
                confidence=model_result.confidence,
            )
            model = settings.AI_MODEL
            await self.interactions.mark_completed(
                interaction,
                response_text=response.content,
                response_data=result.model_dump(mode="json"),
                provider_name=response.provider_name,
                model=model,
                provider_request_id=(
                    str(response.request_id) if response.request_id else None
                ),
            )
            await self.usage.record(
                user_id=user_id,
                feature=AIFunction.ANALYTICS_ASSISTANT.value,
                model=model or "",
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                response_time=elapsed,
                commit=True,
            )
            return AIAnalyticsResponse(
                interaction_id=interaction.id,
                ai_function=interaction.ai_function,
                prompt_id=interaction.prompt_id,
                status=interaction.status,
                provider_name=response.provider_name,
                model=model,
                content=response.content,
                result=result,
            )
        except Exception as exc:
            elapsed = int((monotonic() - started) * 1000)
            await self.interactions.mark_failed(interaction.id, str(exc))
            try:
                await self.usage.record(
                    user_id=user_id,
                    feature=AIFunction.ANALYTICS_ASSISTANT.value,
                    model=settings.AI_MODEL or "",
                    input_tokens=0,
                    output_tokens=0,
                    response_time=elapsed,
                    error_message=str(exc),
                    commit=True,
                )
            except Exception:
                pass
            raise
