from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "FinPilot API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal[
        "development",
        "testing",
        "production",
    ] = "development"

    # Database
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    JWT_EXPIRE_MINUTES: int = Field(default=30, gt=0)

    # Administrator
    ADMIN_PASSWORD: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Storage Settings
    STORAGE_TYPE: str = "local"
    STORAGE_PATH: str = "./storage"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024
    ALLOWED_FILE_TYPES: list[str] = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "text/plain",
    ]


settings = Settings()  # type: ignore[call-arg]
