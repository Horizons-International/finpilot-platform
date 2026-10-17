"""Validated application settings and production security guardrails."""

from typing import Literal

from pydantic import EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "FinPilot API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"

    # Database
    DATABASE_URL: str

    # JWT. Explicit upper bounds prevent accidental long-lived credentials.
    SECRET_KEY: str
    JWT_ACCESS_EXPIRE_MINUTES: int = Field(default=30, gt=0, le=60)
    JWT_REFRESH_EXPIRE_DAYS: int = Field(default=7, gt=0, le=30)

    # Administrator bootstrap credentials
    ADMIN_EMAIL: EmailStr
    ADMIN_PASSWORD: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Refuse known placeholder/weak bootstrap secrets in production."""
        if self.ENVIRONMENT != "production":
            return self

        secret = self.SECRET_KEY.strip()
        weak_values = {
            "secret",
            "changeme",
            "change-me",
            "change-this-secret-key",
            "your-secret-key",
            "development-secret",
        }
        if len(secret) < 32 or len(set(secret)) < 8 or secret.casefold() in weak_values:
            raise ValueError(
                "Production SECRET_KEY must be a unique, high-entropy value "
                "containing at least 32 characters. Generate one with a "
                "cryptographically secure random generator."
            )

        password = self.ADMIN_PASSWORD
        password_is_strong = (
            len(password) >= 12
            and any(char.isupper() for char in password)
            and any(char.islower() for char in password)
            and any(char.isdigit() for char in password)
            and any(not char.isalnum() for char in password)
        )
        weak_passwords = {
            "change-this-admin-password",
            "password",
            "password123!",
            "admin123!",
        }
        if not password_is_strong or password.casefold() in weak_passwords:
            raise ValueError(
                "Production ADMIN_PASSWORD must be at least 12 characters and "
                "contain uppercase, lowercase, numeric, and special characters."
            )
        return self

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
    AI_MODEL_VERSION: str = "unspecified"
    AI_MAX_TOKENS: int = Field(default=1000, gt=0)
    AI_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)
    AI_TIMEOUT: int = Field(default=30, gt=0)
    AI_MAX_CONTEXT_CHARACTERS: int = Field(default=30000, gt=0)

    # Communication Providers
    EMAIL_PROVIDER: str = "mock"
    SMS_PROVIDER: str = "mock"
    EMAIL_FROM_ADDRESS: str = ""
    SMS_FROM_NUMBER: str = ""

    # SLA Monitoring
    SLA_APPROACHING_THRESHOLD_PERCENT: float = Field(default=20.0, gt=0.0, le=100.0)
    SLA_MONITOR_INTERVAL_SECONDS: int = Field(default=60, gt=0)

    # Reporting Exports
    REPORT_ASYNC_ROW_THRESHOLD: int = Field(default=5000, gt=0)
    REPORT_MAX_ROWS: int = Field(default=100_000, gt=0)
    REPORT_EXPORT_INTERVAL_SECONDS: int = Field(default=5, gt=0)

    # User Invitations
    USER_INVITATION_EXPIRE_HOURS: int = Field(default=48, gt=0, le=168)

    # Webhook delivery/retry configuration
    WEBHOOK_ENCRYPTION_KEY: str = ""
    WEBHOOK_DELIVERY_INTERVAL_SECONDS: int = Field(default=5, gt=0)
    WEBHOOK_DELIVERY_TIMEOUT_SECONDS: int = Field(default=10, gt=0, le=60)
    WEBHOOK_MAX_DELIVERY_ATTEMPTS: int = Field(default=8, gt=0, le=20)
    WEBHOOK_RETRY_BASE_SECONDS: int = Field(default=30, gt=0)

    # Enterprise security policy and login monitoring
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=12, le=128)
    LOGIN_FAILURE_THRESHOLD: int = Field(default=5, ge=3, le=20)
    LOGIN_FAILURE_WINDOW_MINUTES: int = Field(default=15, ge=1, le=120)

    # Request-level defensive controls. Tune to measured traffic patterns.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)
    RATE_LIMIT_REQUESTS_PER_IP: int = Field(default=3000, ge=1)
    RATE_LIMIT_REQUESTS_PER_ROUTE: int = Field(default=600, ge=1)
    RATE_LIMIT_AUTH_REQUESTS: int = Field(default=120, ge=1)
    RATE_LIMIT_MAX_TRACKED_KEYS: int = Field(default=20_000, ge=100)
    MAX_REQUEST_BODY_BYTES: int = Field(default=12 * 1024 * 1024, ge=1024)

    # Session policy
    SESSION_IDLE_TIMEOUT_MINUTES: int = Field(default=60, ge=1, le=1440)

    # Response protection
    SECURITY_HEADERS_ENABLED: bool = True
    HSTS_MAX_AGE_SECONDS: int = Field(default=31_536_000, ge=0, le=63_072_000)


settings = Settings()  # type: ignore[call-arg]
