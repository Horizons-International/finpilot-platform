from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import KnowledgeDocumentCategory


class RetrievalResult(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    chunk_id: UUID
    document_id: UUID

    document_name: str
    category: KnowledgeDocumentCategory
    version: int

    content: str

    similarity: float


class RetrievalResponse(BaseModel):
    results: list[RetrievalResult]


class RetrievalRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=5000,
    )

    limit: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    category: KnowledgeDocumentCategory | None = None
