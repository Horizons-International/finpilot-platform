from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import (
    MetricCategory,
    MetricStatus,
    MetricValueType,
)


class RatioMetricDefinition(BaseModel):
    type: Literal["ratio"]
    numerator: str = Field(
        min_length=1,
        max_length=100,
    )
    denominator: str = Field(
        min_length=1,
        max_length=100,
    )
    multiplier: float = Field(
        default=100.0,
        ge=0,
    )
    precision: int = Field(
        default=2,
        ge=0,
        le=6,
    )


class AverageDurationMetricDefinition(BaseModel):
    type: Literal["average_duration"]
    measure: str = Field(
        min_length=1,
        max_length=100,
    )
    precision: int = Field(
        default=2,
        ge=0,
        le=6,
    )


MetricCalculationDefinition = Annotated[
    RatioMetricDefinition | AverageDurationMetricDefinition,
    Field(discriminator="type"),
]


class MetricDefinitionCreate(BaseModel):
    key: str = Field(
        min_length=1,
        max_length=150,
        pattern=r"^[a-z0-9_]+$",
    )

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str = Field(
        min_length=1,
    )

    category: MetricCategory

    value_type: MetricValueType

    definition: MetricCalculationDefinition

    status: MetricStatus = MetricStatus.ACTIVE

    @model_validator(mode="after")
    def validate_definition_type(self) -> "MetricDefinitionCreate":
        if (
            isinstance(
                self.definition,
                RatioMetricDefinition,
            )
            and self.value_type != MetricValueType.PERCENTAGE
        ):
            raise ValueError(
                "Ratio metrics must use PERCENTAGE value_type.",
            )

        if (
            isinstance(
                self.definition,
                AverageDurationMetricDefinition,
            )
            and self.value_type != MetricValueType.SECONDS
        ):
            raise ValueError(
                "Average duration metrics must use SECONDS value_type.",
            )

        return self


class MetricDefinitionUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        min_length=1,
    )

    category: MetricCategory | None = None

    value_type: MetricValueType | None = None

    definition: MetricCalculationDefinition | None = None

    status: MetricStatus | None = None


class MetricDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str
    description: str
    category: MetricCategory
    value_type: MetricValueType
    definition: dict
    status: MetricStatus
    created_at: datetime
    updated_at: datetime


class MetricResultResponse(BaseModel):
    id: UUID
    metric_key: str
    metric_name: str
    category: MetricCategory
    value_type: MetricValueType
    period_start: date
    period_end: date
    value: float | None
    calculated_at: datetime


class MetricCalculationRequest(BaseModel):
    start_date: date
    end_date: date

    metric_keys: list[str] | None = Field(
        default=None,
        min_length=1,
    )

    category: MetricCategory | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "MetricCalculationRequest":
        if self.end_date < self.start_date:
            raise ValueError(
                "end_date must be greater than or equal to start_date.",
            )

        return self
