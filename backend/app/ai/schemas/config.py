from pydantic import BaseModel, Field


class AIConfig(BaseModel):
    provider: str = Field(min_length=1)
    api_key: str = ""
    model: str = ""
    max_tokens: int = Field(default=1000, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout: int = Field(default=30, gt=0)
