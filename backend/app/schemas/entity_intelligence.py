"""Request and response schemas for entity-intelligence graph APIs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EntityNodeCreate(BaseModel):
    entity_type: str = Field(
        min_length=2,
        max_length=40,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
    )
    entity_key: str = Field(min_length=1, max_length=255)
    label: str = Field(min_length=1, max_length=255)
    source_type: str | None = Field(default=None, max_length=64)
    source_id: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)
    risk_score: int = Field(default=0, ge=0, le=100)

    @field_validator("entity_type")
    @classmethod
    def normalize_entity_type(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("entity_key", "label")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be blank.")
        return normalized


class EntityRelationshipCreate(BaseModel):
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str = Field(
        min_length=2,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relationship_type")
    @classmethod
    def normalize_relationship_type(cls, value: str) -> str:
        return value.strip().upper()


class EntityNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    entity_type: str
    entity_key: str
    label: str
    source_type: str | None
    source_id: str | None
    attributes: dict[str, Any]
    risk_score: int
    risk_level: str
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EntityRelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str
    confidence: float
    risk_score: int
    risk_level: str
    risk_indicators: list[str]
    evidence: dict[str, Any]
    observed_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EntityGraphResponse(BaseModel):
    root_entity_id: UUID
    depth: int
    nodes: list[EntityNodeResponse]
    relationships: list[EntityRelationshipResponse]
    risk_relationships: list[EntityRelationshipResponse]


class EntityIntelligenceSyncResponse(BaseModel):
    customer_id: UUID
    transactions_indexed: int
    nodes_indexed: int
    relationships_indexed: int
    risk_relationships_identified: int
    message: str
