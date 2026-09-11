from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AIResponse:
    provider_name: str
    request_type: str
    content: str
    structured_data: dict[str, Any] | None = None
    request_id: UUID | None = None
