import re
from collections.abc import Callable
from time import monotonic
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.exceptions import AIProviderError
from app.ai.prompts.loader import AIPromptLoader
from app.ai.prompts.regulatory import (
    DEFAULT_REGULATORY_SYSTEM_PROMPT,
    build_regulatory_prompt,
)
from app.ai.providers.factory import get_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.ai_service import AIService
from app.core.config import settings
from app.rag.retrieval import RetrievalService
from app.schemas.ai_assistant import AIComplianceResult
from app.schemas.rag import RetrievalResult
from app.schemas.regulatory_assistant import (
    REGULATORY_KNOWLEDGE_CATEGORIES,
    RegulatoryAssistantAnswerResponse,
    RegulatoryAssistantRequest,
    RegulatoryAssistantSearchResponse,
    RegulatoryAssistantSource,
)
from app.services.ai_usage_service import AIUsageService
from app.services.tenant_context import resolve_tenant_context
from app.utils.enums import AIFunction, KnowledgeDocumentCategory

SOURCE_EXCERPT_MAX_CHARACTERS = 700
CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


class RegulatoryAssistantService:
    """Tenant-scoped regulatory Q&A grounded in active knowledge-base chunks."""

    def __init__(
        self,
        db: Session,
        *,
        tenant_id: UUID,
        user_id: UUID,
        retrieval_service: RetrievalService | None = None,
        retrieval_service_factory: Callable[[], RetrievalService] | None = None,
        ai_service: AIService | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_context(
            db,
            tenant_id,
            resource_name="regulatory assistant",
        )
        self.user_id = user_id
        self.retrieval_service = retrieval_service
        self.retrieval_service_factory = retrieval_service_factory
        self.prompt_loader = AIPromptLoader(db)
        self.usage_service = AIUsageService(db, tenant_id=self.tenant_id)
        self.ai_service = ai_service

    def _get_ai_service(self) -> AIService:
        if self.ai_service is None:
            self.ai_service = AIService(provider=get_ai_provider())
        return self.ai_service

    def _get_retrieval_service(self) -> RetrievalService:
        if self.retrieval_service is None:
            if self.retrieval_service_factory is not None:
                self.retrieval_service = self.retrieval_service_factory()
            else:
                self.retrieval_service = RetrievalService(
                    self.db,
                    tenant_id=self.tenant_id,
                )

        return self.retrieval_service

    def _retrieve(
        self,
        *,
        question: str,
        limit: int,
        category: KnowledgeDocumentCategory | None,
    ) -> list[RetrievalResult]:
        if category is not None:
            if category not in REGULATORY_KNOWLEDGE_CATEGORIES:
                raise ValueError(
                    "Unsupported category for regulatory knowledge search."
                )
            return self._get_retrieval_service().retrieve(
                query=question,
                limit=limit,
                category=category,
            )

        return self._get_retrieval_service().retrieve(
            query=question,
            limit=limit,
            categories=set(REGULATORY_KNOWLEDGE_CATEGORIES),
        )

    @staticmethod
    def _sources(results: list[RetrievalResult]) -> list[RegulatoryAssistantSource]:
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

    def search(
        self,
        request: RegulatoryAssistantRequest,
    ) -> RegulatoryAssistantSearchResponse:
        results = self._retrieve(
            question=request.question,
            limit=request.retrieval_limit,
            category=request.category,
        )
        sources = self._sources(results)
        return RegulatoryAssistantSearchResponse(
            query=request.question,
            result_count=len(sources),
            sources=sources,
        )

    def _load_system_prompt(self) -> tuple[str, UUID | None]:
        """Use the tenant's assigned Compliance Review prompt when configured.

        Some tenants may not yet have an assignment for this capability. The
        built-in prompt keeps the endpoint usable while still preferring the
        prompt-management record when it is present and active.
        """
        try:
            prompt = self.prompt_loader.get_prompt(AIFunction.COMPLIANCE_REVIEW)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return DEFAULT_REGULATORY_SYSTEM_PROMPT, None

        return prompt.prompt_text, prompt.id

    @staticmethod
    def _validated_citations(
        answer: str,
        sources: list[RegulatoryAssistantSource],
    ) -> str:
        valid_references = {source.reference for source in sources}
        found = set(CITATION_PATTERN.findall(answer))
        invalid = found - valid_references
        if invalid:
            answer = CITATION_PATTERN.sub(
                lambda match: (
                    match.group(0) if match.group(1) in valid_references else ""
                ),
                answer,
            )

        if not (set(CITATION_PATTERN.findall(answer)) & valid_references):
            citations = ", ".join(f"[{source.reference}]" for source in sources)
            answer = f"{answer.rstrip()}\n\nSupporting sources: {citations}"
        return answer

    def ask(
        self,
        request: RegulatoryAssistantRequest,
    ) -> RegulatoryAssistantAnswerResponse:
        started_at = monotonic()
        query_id = uuid4()
        model_name = settings.AI_MODEL or ""
        provider_name = "knowledge-base"
        prompt_id: UUID | None = None
        input_tokens = 0
        output_tokens = 0

        try:
            results = self._retrieve(
                question=request.question,
                limit=request.retrieval_limit,
                category=request.category,
            )
            sources = self._sources(results)

            if not sources:
                elapsed = int((monotonic() - started_at) * 1000)
                self.usage_service.record(
                    user_id=self.user_id,
                    feature="REGULATORY_ASSISTANT",
                    model=model_name,
                    input_tokens=0,
                    output_tokens=0,
                    response_time=elapsed,
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
                    provider_name=provider_name,
                    model=settings.AI_MODEL,
                )

            system_prompt, prompt_id = self._load_system_prompt()
            prompt_sources = [
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
            response = self._get_ai_service().generate(
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
            provider_name = response.provider_name
            input_tokens = response.input_tokens
            output_tokens = response.output_tokens
            model_name = settings.AI_MODEL or ""
            elapsed = int((monotonic() - started_at) * 1000)
            self.usage_service.record(
                user_id=self.user_id,
                feature="REGULATORY_ASSISTANT",
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                response_time=elapsed,
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
                provider_name=provider_name,
                model=settings.AI_MODEL,
            )
        except Exception as exc:
            elapsed = int((monotonic() - started_at) * 1000)
            self.db.rollback()
            self.usage_service.record(
                user_id=self.user_id,
                feature="REGULATORY_ASSISTANT",
                model=model_name,
                input_tokens=0,
                output_tokens=0,
                response_time=elapsed,
                error_message=str(exc),
            )
            raise
