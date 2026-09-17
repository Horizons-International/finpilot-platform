from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
)


class KnowledgeDocumentCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )

    category: KnowledgeDocumentCategory


class KnowledgeDocumentVersionCreate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    category: KnowledgeDocumentCategory | None = None


class KnowledgeDocumentStatusUpdate(BaseModel):
    status: KnowledgeDocumentStatus


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    name: str
    category: KnowledgeDocumentCategory
    file_reference: str
    version: int
    status: KnowledgeDocumentStatus
    uploaded_by: UUID
    created_at: datetime
