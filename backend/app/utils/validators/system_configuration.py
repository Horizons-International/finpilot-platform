import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import (
    SystemConfigurationCategory,
)

KEY_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
)


class WorkflowConfigurationValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    auto_start: bool | None = None
    default_due_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
    )
    max_steps: int | None = Field(
        default=None,
        ge=1,
        le=100,
    )

    @model_validator(mode="after")
    def validate_not_empty(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("Workflow configuration cannot be empty.")

        return self


class NotificationTemplateConfigurationValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(
        min_length=1,
        max_length=255,
    )

    body: str = Field(
        min_length=1,
        max_length=10000,
    )

    channels: list[str] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_channels(self):
        allowed_channels = {
            "IN_APP",
            "EMAIL",
            "SMS",
            "PUSH",
        }

        invalid_channels = set(self.channels) - allowed_channels

        if invalid_channels:
            raise ValueError(
                "Invalid notification channel(s): "
                + ", ".join(sorted(invalid_channels))
            )

        return self


class SLAConfigurationValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approaching_threshold_percent: float | None = Field(
        default=None,
        gt=0,
        le=100,
    )

    monitor_interval_seconds: int | None = Field(
        default=None,
        gt=0,
        le=86400,
    )

    default_due_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
    )

    @model_validator(mode="after")
    def validate_not_empty(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("SLA configuration cannot be empty.")

        return self


class RiskConfigurationValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_max_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    medium_max_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    high_min_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    critical_min_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    @model_validator(mode="after")
    def validate_thresholds(self):
        values = self.model_dump(exclude_none=True)

        if not values:
            raise ValueError("Risk configuration cannot be empty.")

        low_max = values.get("low_max_score")
        medium_max = values.get("medium_max_score")
        high_min = values.get("high_min_score")
        critical_min = values.get("critical_min_score")

        if low_max is not None and medium_max is not None and low_max >= medium_max:
            raise ValueError("low_max_score must be less than medium_max_score.")

        if medium_max is not None and high_min is not None and medium_max >= high_min:
            raise ValueError("medium_max_score must be less than high_min_score.")

        if (
            high_min is not None
            and critical_min is not None
            and high_min >= critical_min
        ):
            raise ValueError("high_min_score must be less than critical_min_score.")

        return self


class DocumentConfigurationValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_file_size_mb: float | None = Field(
        default=None,
        gt=0,
        le=1024,
    )

    max_documents_per_customer: int | None = Field(
        default=None,
        ge=1,
        le=1000,
    )

    allowed_file_types: list[str] | None = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_not_empty(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("Document configuration cannot be empty.")

        return self


CONFIGURATION_VALUE_MODELS: dict[
    SystemConfigurationCategory,
    type[BaseModel],
] = {
    SystemConfigurationCategory.WORKFLOW: WorkflowConfigurationValue,
    SystemConfigurationCategory.NOTIFICATION_TEMPLATE: (
        NotificationTemplateConfigurationValue
    ),
    SystemConfigurationCategory.SLA: SLAConfigurationValue,
    SystemConfigurationCategory.RISK: RiskConfigurationValue,
    SystemConfigurationCategory.DOCUMENT: DocumentConfigurationValue,
}


def validate_configuration(
    *,
    key: str,
    category: SystemConfigurationCategory,
    value: dict[str, Any],
) -> dict[str, Any]:
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError(
            "Configuration key must use dot notation, "
            "for example 'sla.rules' or 'workflow.settings'."
        )

    expected_prefix = category.value.lower() + "."

    if not key.startswith(expected_prefix):
        raise ValueError(f"Configuration key must start with '{expected_prefix}'.")

    if not isinstance(value, dict) or not value:
        raise ValueError("Configuration value must be a non-empty JSON object.")

    model = CONFIGURATION_VALUE_MODELS[category]

    validated = model.model_validate(value)

    return validated.model_dump(
        mode="json",
        exclude_none=True,
    )
