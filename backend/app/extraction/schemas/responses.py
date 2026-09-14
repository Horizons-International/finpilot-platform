from datetime import date

from pydantic import BaseModel, ConfigDict


class DocumentExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    document_number: str | None = None
    expiry_date: date | None = None
    address: str | None = None
