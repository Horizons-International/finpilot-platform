from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.compliance_reports import (
    AMLAlertsReportResponse,
    ComplianceCasesReportResponse,
    ComplianceReportFilters,
    CustomerRiskReportResponse,
)
from app.services.async_service_bridge import run_sync_in_tenant
from app.services.compliance_report_service import ComplianceReportService
from app.utils.enums import CustomerRiskLevel, UserRole
from app.utils.errors import bad_request

router = APIRouter(prefix="/api/v1/reports", tags=["Compliance Reports"])


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


async def _build_report(
    db: AsyncSession,
    current_user: dict[str, Any],
    filters: ComplianceReportFilters,
    method_name: str,
) -> Any:
    tenant_id = UUID(current_user["tenant_id"])

    def operation(sync_db: Session):
        service = ComplianceReportService(db=sync_db, tenant_id=tenant_id)
        return getattr(service, method_name)(filters)

    return await run_sync_in_tenant(db, tenant_id, operation)


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
    filters = _build_filters(start_date, end_date, country, risk_level)
    report = await _build_report(
        db, current_user, filters, "get_compliance_cases_report"
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
    filters = _build_filters(start_date, end_date, country, risk_level)
    report = await _build_report(db, current_user, filters, "get_aml_alerts_report")
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
    filters = _build_filters(start_date, end_date, country, risk_level)
    report = await _build_report(db, current_user, filters, "get_customer_risk_report")
    return APIResponse(
        success=True,
        message="Customer risk report generated successfully.",
        data=report,
    )
