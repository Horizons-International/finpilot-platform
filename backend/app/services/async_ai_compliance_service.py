"""Native-async compliance/customer/document AI assistant orchestration."""

from time import monotonic
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AIProviderError
from app.ai.prompts.compliance import build_compliance_prompt
from app.ai.providers.async_factory import get_async_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.async_ai_service import AsyncAIService
from app.core.config import settings
from app.rag.async_retrieval import AsyncRetrievalService
from app.schemas.ai_assistant import (
    AIComplianceRequest,
    AIComplianceResponse,
    AIComplianceResult,
)
from app.services.async_ai_context_service import AsyncAIContextService
from app.services.async_ai_interaction_store import AsyncAIInteractionStore
from app.services.async_ai_prompt_loader import AsyncAIPromptLoader
from app.services.async_ai_usage_service import AsyncAIUsageService
from app.utils.errors import bad_request


class AsyncAIComplianceService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        retrieval_service: AsyncRetrievalService | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.retrieval_service = retrieval_service
        self.context_service = AsyncAIContextService(db, tenant_id)
        self.prompt_loader = AsyncAIPromptLoader(db, tenant_id)
        self.interactions = AsyncAIInteractionStore(db, tenant_id)
        self.usage = AsyncAIUsageService(db, tenant_id)

    async def ask(
        self,
        request: AIComplianceRequest,
        *,
        user_id: UUID,
    ) -> AIComplianceResponse:
        context, resource_type, resource_id = await self.context_service.build_context(
            request.ai_function,
            customer_id=request.customer_id,
            verification_case_id=request.verification_case_id,
            document_id=request.document_id,
        )
        if self.retrieval_service is None:
            raise bad_request("Retrieval service is not configured.")
        retrieved = await self.retrieval_service.retrieve(
            query=request.question,
            limit=request.retrieval_limit,
            category=request.knowledge_category,
        )
        context["knowledge_base"] = {
            "query": request.question,
            "results": [item.model_dump(mode="json") for item in retrieved],
        }
        prompt_record = await self.prompt_loader.get_prompt(request.ai_function)
        prompt = build_compliance_prompt(
            system_prompt=prompt_record.prompt_text,
            question=request.question,
            context=context,
        )
        interaction = await self.interactions.create_pending(
            user_id=user_id,
            ai_function=request.ai_function,
            prompt_id=prompt_record.id,
            resource_type=resource_type,
            resource_id=resource_id,
            question=request.question,
            context=context,
        )
        started = monotonic()
        try:
            async with AsyncAIService(provider=get_async_ai_provider()) as ai:
                response = await ai.generate(
                    AIRequest(
                        request_type=AIRequestType.COMPLIANCE_ASSISTANT,
                        prompt=prompt,
                        customer_id=request.customer_id,
                        document_id=request.document_id,
                        structured=True,
                    )
                )
            elapsed = int((monotonic() - started) * 1000)
            if response.structured_data is None:
                raise AIProviderError(
                    "AI provider did not return structured compliance data."
                )
            result = AIComplianceResult.model_validate(response.structured_data)
            model = settings.AI_MODEL
            await self.interactions.mark_completed(
                interaction,
                response_text=response.content,
                response_data=response.structured_data,
                provider_name=response.provider_name,
                model=model,
                provider_request_id=(
                    str(response.request_id) if response.request_id else None
                ),
            )
            await self.usage.record(
                user_id=user_id,
                feature=request.ai_function.value,
                model=model or "",
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                response_time=elapsed,
                commit=True,
            )
            return AIComplianceResponse(
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
                    feature=request.ai_function.value,
                    model=settings.AI_MODEL or "",
                    input_tokens=0,
                    output_tokens=0,
                    response_time=elapsed,
                    error_message=str(exc),
                    commit=True,
                )
            except Exception:
                # Preserve the original provider/orchestration exception.
                pass
            raise
