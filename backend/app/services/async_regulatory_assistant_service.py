"""Native-async regulatory knowledge search and source-grounded Q&A."""

import re
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AIProviderError
from app.ai.prompts.regulatory import (
    DEFAULT_REGULATORY_SYSTEM_PROMPT,
    build_regulatory_prompt,
)
from app.ai.providers.async_factory import get_async_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.async_ai_service import AsyncAIService
from app.core.config import settings
from app.rag.async_retrieval import AsyncRetrievalService
from app.schemas.ai_assistant import AIComplianceResult
from app.schemas.rag import RetrievalResult
from app.schemas.regulatory_assistant import (
    REGULATORY_KNOWLEDGE_CATEGORIES,
    RegulatoryAssistantAnswerResponse,
    RegulatoryAssistantRequest,
    RegulatoryAssistantSearchResponse,
    RegulatoryAssistantSource,
)
from app.services.async_ai_prompt_loader import AsyncAIPromptLoader
from app.services.async_ai_usage_service import AsyncAIUsageService
from app.utils.enums import AIFunction
from app.utils.errors import bad_request

SOURCE_EXCERPT_MAX_CHARACTERS = 700
CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


class AsyncRegulatoryAssistantService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID,
        retrieval_service: AsyncRetrievalService | None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.retrieval_service = retrieval_service
        self.prompt_loader = AsyncAIPromptLoader(db, tenant_id)
        self.usage = AsyncAIUsageService(db, tenant_id)

    async def _retrieve(
        self, request: RegulatoryAssistantRequest
    ) -> list[RetrievalResult]:
        if self.retrieval_service is None:
            raise bad_request("Retrieval service is not configured.")
        if request.category is not None:
            if request.category not in REGULATORY_KNOWLEDGE_CATEGORIES:
                raise bad_request(
                    "Unsupported category for regulatory knowledge search."
                )
            return await self.retrieval_service.retrieve(
                query=request.question,
                limit=request.retrieval_limit,
                category=request.category,
            )
        return await self.retrieval_service.retrieve(
            query=request.question,
            limit=request.retrieval_limit,
            categories=set(REGULATORY_KNOWLEDGE_CATEGORIES),
        )

    @staticmethod
    def _sources(
        results: list[RetrievalResult],
    ) -> list[RegulatoryAssistantSource]:
        return [
            RegulatoryAssistantSource(
                reference=f"S{index}",
                document_id=result.document_id,
                chunk_id=result.chunk_id,
                title=result.document_name,
                category=result.category,
                version=result.version,
                excerpt=result.content[:SOURCE_EXCERPT_MAX_CHARACTERS],
                similarity=round(result.similarity, 4),
            )
            for index, result in enumerate(results, start=1)
        ]

    async def search(
        self, request: RegulatoryAssistantRequest
    ) -> RegulatoryAssistantSearchResponse:
        sources = self._sources(await self._retrieve(request))
        return RegulatoryAssistantSearchResponse(
            query=request.question,
            result_count=len(sources),
            sources=sources,
        )

    async def _load_system_prompt(self) -> tuple[str, UUID | None]:
        try:
            record = await self.prompt_loader.get_prompt(AIFunction.COMPLIANCE_REVIEW)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return DEFAULT_REGULATORY_SYSTEM_PROMPT, None
        return record.prompt_text, record.id

    @staticmethod
    def _validated_citations(
        answer: str,
        sources: list[RegulatoryAssistantSource],
    ) -> str:
        valid = {source.reference for source in sources}
        answer = CITATION_PATTERN.sub(
            lambda match: match.group(0) if match.group(1) in valid else "",
            answer,
        )
        if not (set(CITATION_PATTERN.findall(answer)) & valid):
            citations = ", ".join(f"[{source.reference}]" for source in sources)
            answer = f"{answer.rstrip()}\n\nSupporting sources: {citations}"
        return answer

    async def ask(
        self, request: RegulatoryAssistantRequest
    ) -> RegulatoryAssistantAnswerResponse:
        started = monotonic()
        query_id = uuid4()
        model_name = settings.AI_MODEL or ""
        try:
            sources = self._sources(await self._retrieve(request))
            if not sources:
                elapsed = int((monotonic() - started) * 1000)
                await self.usage.record(
                    user_id=self.user_id,
                    feature="REGULATORY_ASSISTANT",
                    model=model_name,
                    input_tokens=0,
                    output_tokens=0,
                    response_time=elapsed,
                    commit=True,
                )
                return RegulatoryAssistantAnswerResponse(
                    query_id=query_id,
                    question=request.question,
                    answer=(
                        "I could not find a relevant active compliance policy, "
                        "internal procedure, or regulatory guideline in this "
                        "tenant's approved knowledge base. I cannot provide a "
                        "source-grounded answer yet. Ask your compliance owner "
                        "to add or activate the relevant document."
                    ),
                    key_points=[],
                    recommendation=(
                        "Confirm the applicable source document with your "
                        "compliance owner and add it to the approved knowledge base."
                    ),
                    limitations=(
                        "No applicable knowledge sources were retrieved; no "
                        "regulatory conclusion was generated."
                    ),
                    confidence=0.0,
                    source_count=0,
                    sources=[],
                    prompt_id=None,
                    provider_name="knowledge-base",
                    model=settings.AI_MODEL,
                )

            system_prompt, prompt_id = await self._load_system_prompt()
            prompt_sources: list[dict[str, Any]] = [
                {
                    "reference": f"[{source.reference}]",
                    "document_id": str(source.document_id),
                    "chunk_id": str(source.chunk_id),
                    "title": source.title,
                    "category": source.category.value,
                    "version": source.version,
                    "similarity": source.similarity,
                    "content": source.excerpt,
                }
                for source in sources
            ]
            prompt = build_regulatory_prompt(
                system_prompt=system_prompt,
                question=request.question,
                sources=prompt_sources,
            )
            async with AsyncAIService(provider=get_async_ai_provider()) as ai:
                response = await ai.generate(
                    AIRequest(
                        request_type=AIRequestType.COMPLIANCE_ASSISTANT,
                        prompt=prompt,
                        structured=True,
                    )
                )
            if response.structured_data is None:
                raise AIProviderError(
                    "AI provider returned no structured regulatory answer."
                )
            result = AIComplianceResult.model_validate(response.structured_data)
            answer = self._validated_citations(result.summary, sources)
            elapsed = int((monotonic() - started) * 1000)
            await self.usage.record(
                user_id=self.user_id,
                feature="REGULATORY_ASSISTANT",
                model=model_name,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                response_time=elapsed,
                commit=True,
            )
            return RegulatoryAssistantAnswerResponse(
                query_id=query_id,
                question=request.question,
                answer=answer,
                key_points=result.findings,
                recommendation=result.recommendation,
                limitations=(
                    "This response summarizes retrieved information and is not a "
                    "final legal opinion or binding regulatory determination."
                ),
                confidence=max(0.0, min(1.0, result.confidence)),
                source_count=len(sources),
                sources=sources,
                prompt_id=prompt_id,
                provider_name=response.provider_name,
                model=settings.AI_MODEL,
            )
        except Exception as exc:
            elapsed = int((monotonic() - started) * 1000)
            try:
                await self.usage.record(
                    user_id=self.user_id,
                    feature="REGULATORY_ASSISTANT",
                    model=model_name,
                    input_tokens=0,
                    output_tokens=0,
                    response_time=elapsed,
                    error_message=str(exc),
                    commit=True,
                )
            except Exception:
                pass
            raise
