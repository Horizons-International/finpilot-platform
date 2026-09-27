from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.compliance_reports import (
    AMLAlertsReportResponse,
    ComplianceCasesReportResponse,
    ComplianceReportFilters,
    CustomerRiskReportResponse,
)
from app.services.compliance_report_service import (
    ComplianceReportService,
)
from app.utils.enums import (
    CustomerRiskLevel,
    UserRole,
)
from app.utils.errors import bad_request

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Compliance Reports"],
)


def _build_filters(
    start_date: date | None,
    end_date: date | None,
    country: str | None,
    risk_level: CustomerRiskLevel | None,
) -> ComplianceReportFilters:
    try:
        return ComplianceReportFilters(
            start_date=start_date,
            end_date=end_date,
            country=country,
            risk_level=risk_level,
        )
    except ValidationError:
        raise bad_request("start_date cannot be later than end_date.")


@router.get(
    "/compliance-cases",
    response_model=APIResponse[ComplianceCasesReportResponse],
    status_code=status.HTTP_200_OK,
    summary="Get compliance case report",
    description=(
        "Return compliance case workload statistics including "
        "total, open, closed, and average resolution time. "
        "Administrators and compliance officers can access "
        "the report."
    ),
)
def get_compliance_cases_report(
    start_date: date | None = Query(
        default=None,
        description="Inclusive report start date.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive report end date.",
    ),
    country: str | None = Query(
        default=None,
        description="Customer country of residence.",
    ),
    risk_level: CustomerRiskLevel | None = Query(
        default=None,
        description="Customer risk level.",
    ),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="compliance_report",
        )
    ),
) -> APIResponse[ComplianceCasesReportResponse]:
    filters = _build_filters(
        start_date=start_date,
        end_date=end_date,
        country=country,
        risk_level=risk_level,
    )

    service = ComplianceReportService(db)

    report = service.get_compliance_cases_report(
        filters,
    )

    return APIResponse(
        success=True,
        message=("Compliance case report generated successfully."),
        data=report,
    )


@router.get(
    "/aml-alerts",
    response_model=APIResponse[AMLAlertsReportResponse],
    status_code=status.HTTP_200_OK,
    summary="Get AML alert report",
    description=(
        "Return AML monitoring alerts grouped by severity, "
        "rule, and current alert status. Administrators and "
        "compliance officers can access the report."
    ),
)
def get_aml_alerts_report(
    start_date: date | None = Query(
        default=None,
        description="Inclusive report start date.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive report end date.",
    ),
    country: str | None = Query(
        default=None,
        description="Transaction country.",
    ),
    risk_level: CustomerRiskLevel | None = Query(
        default=None,
        description="Customer risk level.",
    ),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="compliance_report",
        )
    ),
) -> APIResponse[AMLAlertsReportResponse]:
    filters = _build_filters(
        start_date=start_date,
        end_date=end_date,
        country=country,
        risk_level=risk_level,
    )

    service = ComplianceReportService(db)

    report = service.get_aml_alerts_report(
        filters,
    )

    return APIResponse(
        success=True,
        message="AML alert report generated successfully.",
        data=report,
    )


@router.get(
    "/customer-risk",
    response_model=APIResponse[CustomerRiskReportResponse],
    status_code=status.HTTP_200_OK,
    summary="Get customer risk report",
    description=(
        "Return customer counts by risk level, high-risk "
        "customer totals, and historical risk-level changes. "
        "Administrators and compliance officers can access "
        "the report."
    ),
)
def get_customer_risk_report(
    start_date: date | None = Query(
        default=None,
        description="Inclusive report start date.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive report end date.",
    ),
    country: str | None = Query(
        default=None,
        description="Customer country of residence.",
    ),
    risk_level: CustomerRiskLevel | None = Query(
        default=None,
        description="Current or historical risk level filter.",
    ),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="compliance_report",
        )
    ),
) -> APIResponse[CustomerRiskReportResponse]:
    filters = _build_filters(
        start_date=start_date,
        end_date=end_date,
        country=country,
        risk_level=risk_level,
    )

    service = ComplianceReportService(db)

    report = service.get_customer_risk_report(
        filters,
    )

    return APIResponse(
        success=True,
        message="Customer risk report generated successfully.",
        data=report,
    )
