from typing import Literal

from pydantic import EmailStr, Field
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
    JWT_ACCESS_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    JWT_REFRESH_EXPIRE_DAYS: int = Field(default=7, gt=0)

    # Administrator
    ADMIN_EMAIL: EmailStr
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
    MAX_FILE_SIZE_MB: int = Field(default=10, gt=0)

    @property
    def MAX_FILE_SIZE(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    ALLOWED_FILE_TYPES: list[str] = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "text/plain",
    ]

    # Verification Provider
    VERIFICATION_PROVIDER: str = "mock"
    OCR_PROVIDER: str = "mock"
    EXTRACTION_PROVIDER: str = "mock"

    AI_PROVIDER: str = "mock"
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    AI_MAX_TOKENS: int = Field(default=1000, gt=0)
    AI_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)
    AI_TIMEOUT: int = Field(default=30, gt=0)
    AI_MAX_CONTEXT_CHARACTERS: int = Field(
        default=30000,
        gt=0,
    )

    # Communication Providers
    EMAIL_PROVIDER: str = "mock"
    SMS_PROVIDER: str = "mock"

    EMAIL_FROM_ADDRESS: str = ""
    SMS_FROM_NUMBER: str = ""

    # SLA Monitoring
    SLA_APPROACHING_THRESHOLD_PERCENT: float = Field(
        default=20.0,
        gt=0.0,
        le=100.0,
    )

    SLA_MONITOR_INTERVAL_SECONDS: int = Field(
        default=60,
        gt=0,
    )

    # Reporting Exports
    REPORT_ASYNC_ROW_THRESHOLD: int = Field(
        default=5000,
        gt=0,
    )

    REPORT_MAX_ROWS: int = Field(
        default=100_000,
        gt=0,
    )

    REPORT_EXPORT_INTERVAL_SECONDS: int = Field(
        default=5,
        gt=0,
    )


settings = Settings()  # type: ignore[call-arg]
