from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.enums import (
    AMLRuleSeverity,
    CustomerRiskLevel,
)


class ComplianceReportFilters(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    country: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    risk_level: CustomerRiskLevel | None = None

    @field_validator("country")
    @classmethod
    def normalize_country(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip().upper()

        return normalized or None

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError(
                "start_date cannot be later than end_date.",
            )

        return self


class ComplianceCasesReportResponse(BaseModel):
    total_cases: int
    open_cases: int
    closed_cases: int
    average_resolution_time_hours: float | None


class AMLAlertSeverityCount(BaseModel):
    severity: AMLRuleSeverity
    count: int


class AMLAlertRuleCount(BaseModel):
    rule_id: UUID
    rule_name: str
    severity: AMLRuleSeverity
    count: int


class AMLAlertStatusCount(BaseModel):
    status: str
    count: int


class AMLAlertsReportResponse(BaseModel):
    total_alerts: int
    alerts_by_severity: list[AMLAlertSeverityCount]
    alerts_by_rule: list[AMLAlertRuleCount]
    alert_status: list[AMLAlertStatusCount]


class CustomerRiskLevelCount(BaseModel):
    risk_level: CustomerRiskLevel
    count: int


class CustomerRiskChange(BaseModel):
    assessed_date: date
    previous_risk_level: CustomerRiskLevel
    new_risk_level: CustomerRiskLevel
    count: int


class CustomerRiskReportResponse(BaseModel):
    customers_by_risk_level: list[CustomerRiskLevelCount]
    high_risk_customers: int
    risk_changes_over_time: list[CustomerRiskChange]
