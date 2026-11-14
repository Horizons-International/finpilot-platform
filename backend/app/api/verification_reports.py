from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.report import DocumentSummaryResponse, VerificationSummaryResponse
from app.services.async_report_service import AsyncReportService
from app.utils.enums import DocumentStatus, UserRole, VerificationStatus

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.get(
    "/verification-summary",
    response_model=APIResponse[VerificationSummaryResponse],
    status_code=status.HTTP_200_OK,
)
async def get_verification_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: VerificationStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
            resource_type="verification_summary",
        )
    ),
) -> APIResponse[VerificationSummaryResponse]:
    tenant_id = UUID(current_user["tenant_id"])
    summary = await AsyncReportService(
        db, tenant_id=tenant_id
    ).get_verification_summary(
        date_from=date_from,
        date_to=date_to,
        status=status,
    )
    return APIResponse(
        success=True,
        message="Verification summary retrieved successfully.",
        data=summary,
    )


@router.get("/document-summary", response_model=APIResponse[DocumentSummaryResponse])
async def get_document_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: DocumentStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
            resource_type="verification_summary",
        )
    ),
) -> APIResponse[DocumentSummaryResponse]:
    tenant_id = UUID(current_user["tenant_id"])
    summary = await AsyncReportService(db, tenant_id=tenant_id).get_document_summary(
        date_from=date_from,
        date_to=date_to,
        status=status,
    )
    return APIResponse(
        success=True, message="Document summary retrieved successfully.", data=summary
    )
