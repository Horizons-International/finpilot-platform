from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import AIFunction, AIPromptStatus


class AIPromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=255)
    prompt_text: str = Field(min_length=1)


class AIPromptVersionCreate(BaseModel):
    prompt_text: str = Field(min_length=1)


class AIPromptStatusUpdate(BaseModel):
    status: AIPromptStatus


class AIPromptAssignmentCreate(BaseModel):
    ai_function: AIFunction
    prompt_id: UUID


class AIPromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    purpose: str
    prompt_text: str
    version: int
    status: AIPromptStatus
    created_by: UUID
    created_at: datetime


class AIPromptAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ai_function: AIFunction
    prompt_id: UUID
    created_at: datetime


class AIPromptWithAssignmentResponse(AIPromptResponse):
    ai_function: AIFunction | None = None
