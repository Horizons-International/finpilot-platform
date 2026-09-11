from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.report import (
    DocumentSummaryResponse,
    VerificationSummaryResponse,
)
from app.services.report_service import ReportService
from app.utils.enums import DocumentStatus, UserRole, VerificationStatus

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Reports"],
)


def get_report_service(
    db: Session = Depends(get_db),
) -> ReportService:
    return ReportService(db)


@router.get(
    "/verification-summary",
    response_model=APIResponse[VerificationSummaryResponse],
)
def get_verification_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: VerificationStatus | None = Query(default=None),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
        )
    ),
    service: ReportService = Depends(get_report_service),
) -> APIResponse[VerificationSummaryResponse]:
    summary = service.get_verification_summary(
        date_from=date_from,
        date_to=date_to,
        status=status,
    )

    return APIResponse(
        success=True,
        message="Verification summary retrieved successfully.",
        data=summary,
    )


@router.get(
    "/document-summary",
    response_model=APIResponse[DocumentSummaryResponse],
)
def get_document_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: DocumentStatus | None = Query(default=None),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
        )
    ),
    service: ReportService = Depends(get_report_service),
) -> APIResponse[DocumentSummaryResponse]:
    summary = service.get_document_summary(
        date_from=date_from,
        date_to=date_to,
        status=status,
    )

    return APIResponse(
        success=True,
        message="Document summary retrieved successfully.",
        data=summary,
    )
