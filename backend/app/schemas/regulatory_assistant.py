from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.utils.enums import KnowledgeDocumentCategory

REGULATORY_KNOWLEDGE_CATEGORIES = frozenset(
    {
        KnowledgeDocumentCategory.COMPLIANCE_POLICY,
        KnowledgeDocumentCategory.INTERNAL_PROCEDURE,
        KnowledgeDocumentCategory.REGULATORY_GUIDELINE,
    }
)


class RegulatoryAssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    category: KnowledgeDocumentCategory | None = None
    retrieval_limit: int = Field(default=5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must contain non-whitespace text.")
        return value

    @field_validator("category")
    @classmethod
    def category_must_be_regulatory(
        cls,
        value: KnowledgeDocumentCategory | None,
    ) -> KnowledgeDocumentCategory | None:
        if value is not None and value not in REGULATORY_KNOWLEDGE_CATEGORIES:
            raise ValueError(
                "Regulatory assistant searches support compliance policies, "
                "internal procedures, and regulatory guidelines only."
            )
        return value


class RegulatoryAssistantSource(BaseModel):
    reference: str = Field(description="Citation marker used in the answer, e.g. S1.")
    document_id: UUID
    chunk_id: UUID
    title: str
    category: KnowledgeDocumentCategory
    version: int
    excerpt: str
    similarity: float = Field(ge=0.0, le=1.0)


class RegulatoryAssistantSearchResponse(BaseModel):
    query: str
    result_count: int
    sources: list[RegulatoryAssistantSource]


class RegulatoryAssistantAnswerResponse(BaseModel):
    query_id: UUID
    question: str
    answer: str
    key_points: list[str] = Field(default_factory=list)
    recommendation: str
    limitations: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_count: int
    sources: list[RegulatoryAssistantSource]
    prompt_id: UUID | None = None
    provider_name: str
    model: str | None = None
