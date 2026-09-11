from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class AIRequestType(str, Enum):
    TEXT = "text"
    DOCUMENT_ANALYSIS = "document_analysis"


@dataclass(frozen=True)
class AIRequest:
    request_type: AIRequestType
    prompt: str
    customer_id: UUID | None = None
    document_id: UUID | None = None
    structured: bool = False
