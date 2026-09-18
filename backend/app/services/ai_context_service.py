from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.rag.context import RAGContextBuilder
from app.rag.retrieval import RetrievalService
from app.services.compliance_context_service import (
    ComplianceContextService,
)
from app.utils.enums import (
    AIFunction,
    AIResourceType,
    KnowledgeDocumentCategory,
)


class AIContextService:
    """
    Builds the complete context supplied to the AI assistant.

    Context consists of:

    1. Existing platform/business context.
    2. Relevant knowledge-base context retrieved through RAG.
    """

    def __init__(
        self,
        db: Session,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        self.compliance_context_service = ComplianceContextService(db)

        self.rag_context_builder = RAGContextBuilder(
            retrieval_service=retrieval_service,
        )

    def build_context(
        self,
        ai_function: AIFunction,
        *,
        question: str,
        customer_id: UUID | None = None,
        verification_case_id: UUID | None = None,
        document_id: UUID | None = None,
        knowledge_category: KnowledgeDocumentCategory | None = None,
        retrieval_limit: int = 5,
    ) -> tuple[
        dict[str, Any],
        AIResourceType,
        UUID,
    ]:
        (
            platform_context,
            resource_type,
            resource_id,
        ) = self.compliance_context_service.build_context(
            ai_function,
            customer_id=customer_id,
            verification_case_id=verification_case_id,
            document_id=document_id,
        )

        rag_context = self.rag_context_builder.build(
            query=question,
            category=knowledge_category,
            limit=retrieval_limit,
        )

        combined_context = dict(platform_context)

        combined_context["knowledge_base"] = rag_context

        return (
            combined_context,
            resource_type,
            resource_id,
        )
