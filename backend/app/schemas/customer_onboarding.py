from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CustomerOnboardingAdvanceRequest(BaseModel):
    notes: str | None = Field(
        default=None,
        max_length=2000,
    )

    result: dict[str, Any] | None = None


class CustomerOnboardingFailureRequest(BaseModel):
    notes: str | None = Field(
        default=None,
        max_length=2000,
    )


class CustomerOnboardingResponse(BaseModel):
    execution_id: UUID
    workflow_id: UUID
    customer_id: UUID
    status: str
    current_step_id: UUID | None
    step_executions: list[Any]
