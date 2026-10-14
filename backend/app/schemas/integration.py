"""Validation and response schemas for integration management."""

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import IntegrationStatus, IntegrationType

_SECRET_FIELD_SUFFIXES = (
    "apikey",
    "apikeys",
    "password",
    "passwords",
    "secret",
    "secrets",
    "token",
    "tokens",
    "accesstoken",
    "accesstokens",
    "refreshtoken",
    "refreshtokens",
    "clientsecret",
    "privatekey",
    "authorization",
    "credential",
    "credentials",
)
_SECRET_REFERENCE_SUFFIXES = ("secretref", "credentialref", "passwordref", "tokenref")


def _validate_secret_references(value: Any, path: str = "configuration") -> None:
    """Prevent plain credentials being persisted inside JSON configuration.

    Integrations may instead store references such as ``vault://team/provider``.
    Actual secret resolution belongs in an adapter/secret manager.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            is_reference = normalized.endswith(_SECRET_REFERENCE_SUFFIXES)
            is_sensitive = normalized.endswith(_SECRET_FIELD_SUFFIXES)
            if is_sensitive and not is_reference:
                raise ValueError(
                    f"Do not store credentials at {path}.{key}; "
                    "use a secret reference instead."
                )
            if is_reference:
                if not isinstance(child, str) or not child.strip():
                    raise ValueError(
                        f"Secret reference {path}.{key} must be a non-empty string."
                    )
                if not ("://" in child or child.startswith("arn:") or "/" in child):
                    raise ValueError(
                        f"Secret reference {path}.{key} must identify a "
                        "secret-manager, environment, or provider secret path."
                    )
            _validate_secret_references(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_secret_references(child, f"{path}[{index}]")


class IntegrationCreate(BaseModel):
    provider_name: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$",
    )
    integration_type: IntegrationType
    configuration: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = False

    @field_validator("provider_name")
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("configuration")
    @classmethod
    def validate_configuration(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_secret_references(value)
        return value


class IntegrationUpdate(BaseModel):
    configuration: dict[str, Any]

    @field_validator("configuration")
    @classmethod
    def validate_configuration(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_secret_references(value)
        return value


class IntegrationEnabledUpdate(BaseModel):
    is_enabled: bool


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    provider_name: str
    integration_type: IntegrationType
    configuration: dict[str, Any]
    is_enabled: bool
    status: IntegrationStatus
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class IntegrationCheckResponse(BaseModel):
    integration: IntegrationResponse
    message: str
