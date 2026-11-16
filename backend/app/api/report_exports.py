from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.dependencies import get_report_export_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.report_exports import (
    ReportExportListResponse,
    ReportExportRequest,
    ReportExportResponse,
)
from app.services.async_report_export_query_service import AsyncReportExportQueryService
from app.services.report_export_service import ReportExportService
from app.utils.enums import ReportExportStatus, UserRole

router = APIRouter(prefix="/api/v1/reports", tags=["Report Exports"])

GENERATE_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER)
READ_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER, UserRole.AUDITOR)


def _to_response(report_export) -> ReportExportResponse:
    response = ReportExportResponse.model_validate(report_export)
    if report_export.status == ReportExportStatus.COMPLETED:
        response.download_url = f"/api/v1/reports/exports/{report_export.id}/download"
    return response


def _query_service(
    db: AsyncSession, user: dict[str, Any]
) -> AsyncReportExportQueryService:
    return AsyncReportExportQueryService(db, UUID(user["tenant_id"]))


@router.post(
    "/exports",
    response_model=APIResponse[ReportExportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate report export",
    description=(
        "Generate a CSV, Excel, or PDF export. Large reports are queued for "
        "background processing. This request remains synchronous because "
        "small exports may be generated inline."
    ),
)
def create_report_export(
    request_body: ReportExportRequest,
    response: Response,
    current_user: dict[str, Any] = Depends(
        require_roles(*GENERATE_ROLES, resource_type="report-export")
    ),
    service: ReportExportService = Depends(get_report_export_service),
) -> APIResponse[ReportExportResponse]:
    report_export = service.request_export(
        request=request_body,
        requested_by=UUID(str(current_user["sub"])),
    )
    if report_export.status == ReportExportStatus.REQUESTED:
        response.status_code = status.HTTP_202_ACCEPTED
        message = "Report export accepted and queued for background generation."
    else:
        message = "Report export generated successfully."
    return APIResponse(success=True, message=message, data=_to_response(report_export))


@router.get(
    "/exports",
    response_model=APIResponse[ReportExportListResponse],
    summary="List report export history",
)
async def list_report_exports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="report-export-history")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[ReportExportListResponse]:
    exports, total = await _query_service(db, current_user).list_exports(
        page=page, page_size=page_size
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    data = ReportExportListResponse(
        exports=[_to_response(item) for item in exports],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
    return APIResponse(
        success=True, message="Report export history retrieved successfully.", data=data
    )


@router.get(
    "/exports/{export_id}",
    response_model=APIResponse[ReportExportResponse],
    summary="Get report export status",
)
async def get_report_export(
    export_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="report-export")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[ReportExportResponse]:
    report_export = await _query_service(db, current_user).get_export(export_id)
    return APIResponse(
        success=True,
        message="Report export retrieved successfully.",
        data=_to_response(report_export),
    )


@router.get(
    "/exports/{export_id}/download",
    summary="Download report export",
)
def download_report_export(
    export_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(*READ_ROLES, resource_type="report-export-download")
    ),
    service: ReportExportService = Depends(get_report_export_service),
):
    # The configured storage adapter exposes blocking filesystem operations.
    report_export, content = service.read_export_file(export_id=export_id)
    return Response(
        content=content,
        media_type=report_export.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{report_export.filename}"'
        },
    )
