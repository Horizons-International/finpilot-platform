from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.enums import (
    ComplianceCaseStatus,
    CustomerRiskLevel,
    CustomerStatus,
    ReportExportFormat,
    ReportExportStatus,
    ReportType,
    TaskStatus,
    VerificationStatus,
    VerificationType,
    WorkflowExecutionStatus,
)


class ReportFilters(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    country: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    customer_status: CustomerStatus | None = None
    risk_level: CustomerRiskLevel | None = None

    verification_status: VerificationStatus | None = None
    verification_type: VerificationType | None = None

    compliance_status: ComplianceCaseStatus | None = None

    task_status: TaskStatus | None = None
    workflow_status: WorkflowExecutionStatus | None = None

    @field_validator("country")
    @classmethod
    def normalize_country(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None

    @model_validator(mode="after")
    def validate_date_range(self) -> "ReportFilters":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError(
                "start_date cannot be later than end_date.",
            )

        return self


class ReportExportRequest(BaseModel):
    report_type: ReportType
    format: ReportExportFormat
    filters: ReportFilters = Field(
        default_factory=ReportFilters,
    )
    prefer_async: bool = False


class ReportExportResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    report_type: ReportType
    format: ReportExportFormat
    requested_by: UUID
    filters: dict
    status: ReportExportStatus
    filename: str | None
    content_type: str | None
    file_size: int | None
    row_count: int | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    download_url: str | None = None


class ReportExportListResponse(BaseModel):
    exports: list[ReportExportResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
