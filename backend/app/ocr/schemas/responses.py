from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class OCRResponse:
    provider_name: str
    document_id: UUID
    extracted_text: str
    processing_status: str
    request_id: UUID | None = None
    error_message: str | None = None
