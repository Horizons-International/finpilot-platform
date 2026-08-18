from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    stored_filename: str
    storage_path: str
    folder: str
    module: str
    content_type: str
    file_size: int
    uploaded_by: UUID
    created_at: datetime
