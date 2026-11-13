from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.compliance_reports import (
    AMLAlertsReportResponse,
    ComplianceCasesReportResponse,
    ComplianceReportFilters,
    CustomerRiskReportResponse,
)
from app.services.async_compliance_report_service import AsyncComplianceReportService
from app.utils.enums import CustomerRiskLevel, UserRole
from app.utils.errors import bad_request

router = APIRouter(prefix="/api/v1/reports", tags=["Compliance Reports"])


def _service(
    db: AsyncSession, current_user: dict[str, Any]
) -> AsyncComplianceReportService:
    return AsyncComplianceReportService(db, UUID(current_user["tenant_id"]))


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
    except ValidationError as exc:
        raise bad_request("start_date cannot be later than end_date.") from exc


@router.get(
    "/compliance-cases",
    response_model=APIResponse[ComplianceCasesReportResponse],
    status_code=status.HTTP_200_OK,
)
async def get_compliance_cases_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country: str | None = Query(default=None),
    risk_level: CustomerRiskLevel | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="compliance_report",
        )
    ),
) -> APIResponse[ComplianceCasesReportResponse]:
    report = await _service(db, current_user).get_compliance_cases_report(
        _build_filters(start_date, end_date, country, risk_level)
    )
    return APIResponse(
        success=True,
        message="Compliance case report generated successfully.",
        data=report,
    )


@router.get(
    "/aml-alerts",
    response_model=APIResponse[AMLAlertsReportResponse],
    status_code=status.HTTP_200_OK,
)
async def get_aml_alerts_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country: str | None = Query(default=None),
    risk_level: CustomerRiskLevel | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="compliance_report",
        )
    ),
) -> APIResponse[AMLAlertsReportResponse]:
    report = await _service(db, current_user).get_aml_alerts_report(
        _build_filters(start_date, end_date, country, risk_level)
    )
    return APIResponse(
        success=True, message="AML alert report generated successfully.", data=report
    )


@router.get(
    "/customer-risk",
    response_model=APIResponse[CustomerRiskReportResponse],
    status_code=status.HTTP_200_OK,
)
async def get_customer_risk_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    country: str | None = Query(default=None),
    risk_level: CustomerRiskLevel | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="compliance_report",
        )
    ),
) -> APIResponse[CustomerRiskReportResponse]:
    report = await _service(db, current_user).get_customer_risk_report(
        _build_filters(start_date, end_date, country, risk_level)
    )
    return APIResponse(
        success=True,
        message="Customer risk report generated successfully.",
        data=report,
    )
