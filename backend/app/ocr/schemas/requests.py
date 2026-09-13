from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class OCRRequest:
    document_id: UUID
    file_reference: str
    file_name: str
    file_type: str
