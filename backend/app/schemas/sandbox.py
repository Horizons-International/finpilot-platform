"""Request/response models for sandbox-only workflows."""

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

SUPPORTED_SANDBOX_EVENTS = (
    "customer.created",
    "customer.updated",
    "verification.completed",
    "verification.failed",
)


class SandboxAccountCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    developer_name: str = Field(min_length=2, max_length=200)
    developer_email: EmailStr

    @field_validator("organization_name", "developer_name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized

    @field_validator("developer_email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return cast(EmailStr, str(value).strip().lower())


class SandboxAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_name: str
    developer_name: str
    developer_email: EmailStr
    status: str
    created_at: datetime
    expires_at: datetime


class SandboxOrganizationResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    name: str
    code: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SandboxUserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    role: Literal["DEVELOPER", "OPERATOR", "REVIEWER", "AUDITOR"] = "DEVELOPER"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("User name must not be blank.")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return cast(EmailStr, str(value).strip().lower())


class SandboxUserResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    name: str
    email: EmailStr
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SandboxCustomerCreate(BaseModel):
    external_reference: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = Field(min_length=4, max_length=30)
    attributes: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, max_length=30
    )

    @field_validator("first_name", "last_name", "phone_number")
    @classmethod
    def strip_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return cast(EmailStr, str(value).strip().lower())


class SandboxCustomerResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    external_reference: str
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    status: str
    attributes: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SandboxAccountCreatedResponse(BaseModel):
    environment: Literal["sandbox"] = "sandbox"
    account: SandboxAccountResponse
    organization: SandboxOrganizationResponse
    developer: SandboxUserResponse
    api_key: str = Field(
        description="One-time sandbox key. It cannot be retrieved again."
    )
    sample_customers: list[SandboxCustomerResponse]
    base_path: str = "/api/v1/sandbox"


SandboxAPIKeyPermission = Literal[
    "sandbox:read",
    "sandbox:write",
    "sandbox:webhooks",
    "sandbox:admin",
]


def default_sandbox_api_key_permissions() -> list[SandboxAPIKeyPermission]:
    return [
        "sandbox:read",
        "sandbox:write",
        "sandbox:webhooks",
    ]


class SandboxAPIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    permissions: list[SandboxAPIKeyPermission] = Field(
        default_factory=default_sandbox_api_key_permissions,
        min_length=1,
        max_length=4,
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("API key name must not be blank.")
        return normalized

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Permissions must not contain duplicates.")
        return value


class SandboxAPIKeyResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    name: str
    key_prefix: str
    permissions: list[str]
    status: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class SandboxAPIKeyCreatedResponse(BaseModel):
    key: SandboxAPIKeyResponse
    api_key: str = Field(
        description="One-time sandbox key. It cannot be retrieved again."
    )


class SandboxVerificationCreate(BaseModel):
    scenario: Literal["APPROVED", "REJECTED", "MANUAL_REVIEW"] = "APPROVED"


class SandboxVerificationResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    customer_id: UUID
    scenario: str
    status: str
    result: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SandboxWebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    endpoint_url: AnyHttpUrl | None = None
    event_types: list[str] = Field(
        min_length=1, max_length=len(SUPPORTED_SANDBOX_EVENTS)
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Webhook name must not be blank.")
        return normalized

    @field_validator("event_types")
    @classmethod
    def validate_events(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value))
        if not normalized or any(not item for item in normalized):
            raise ValueError("At least one event type is required.")
        unsupported = sorted(set(normalized) - set(SUPPORTED_SANDBOX_EVENTS))
        if unsupported:
            raise ValueError(
                f"Unsupported sandbox event type(s): {', '.join(unsupported)}"
            )
        return normalized


class SandboxWebhookResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    name: str
    endpoint_url: str | None
    event_types: list[str]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SandboxWebhookSimulationRequest(BaseModel):
    event_type: str
    customer_id: UUID | None = None

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if value not in SUPPORTED_SANDBOX_EVENTS:
            raise ValueError(
                "Unsupported sandbox event. Allowed: "
                f"{', '.join(SUPPORTED_SANDBOX_EVENTS)}"
            )
        return value


class SandboxWebhookEventResponse(BaseModel):
    id: UUID
    sandbox_account_id: UUID
    webhook_id: UUID
    event_type: str
    delivery_status: str
    payload: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
