"""API endpoints for the tenant-scoped compliance documentation library."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_file_service, get_storage
from app.core.responses import APIResponse
from app.core.security import get_current_user, require_roles
from app.models.compliance_document import ComplianceDocumentStatus
from app.models.user import User
from app.schemas.compliance_document import (
    ComplianceApprovalComment,
    ComplianceApprovalResponse,
    ComplianceDocumentResponse,
    ComplianceDocumentVersionResponse,
    ComplianceEvidenceCreate,
    ComplianceEvidenceResponse,
)
from app.services.compliance_document_service import ComplianceDocumentService
from app.services.file_service import FileService
from app.storages.base_storage import BaseStorage
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/compliance-documents",
    tags=["Compliance Documentation"],
)

_READ_ROLES = tuple(UserRole)
_WRITE_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
)
_APPROVER_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
)
_EVIDENCE_TYPES = {
    "ACCESS_CONTROL",
    "ENCRYPTION",
    "MONITORING",
    "KYC_PROCESS",
    "AML_MONITORING",
    "CASE_MANAGEMENT",
    "INCIDENT_MANAGEMENT",
    "BUSINESS_CONTINUITY",
    "CHANGE_MANAGEMENT",
    "OTHER",
}


def get_compliance_document_service(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
    storage: BaseStorage = Depends(get_storage),
) -> ComplianceDocumentService:
    return ComplianceDocumentService(
        db,
        tenant_id=current_user.tenant_id,
        current_user=current_user,
        file_service=file_service,
        storage=storage,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post(
    "",
    response_model=APIResponse[ComplianceDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a compliance document",
)
async def create_compliance_document(
    name: str = Form(..., min_length=1, max_length=255),
    category: str = Form(..., min_length=1, max_length=64),
    file: UploadFile = File(...),
    change_summary: str | None = Form(default="Initial version", max_length=2000),
    _: dict[str, Any] = Depends(
        require_roles(*_WRITE_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceDocumentResponse]:
    document = await service.create_document(
        name=name,
        category=category,
        file=file,
        change_summary=change_summary,
    )
    return APIResponse(
        success=True,
        message="Compliance document created as a draft.",
        data=ComplianceDocumentResponse.model_validate(document),
    )


@router.get(
    "",
    response_model=APIResponse[list[ComplianceDocumentResponse]],
    summary="List tenant compliance documents",
)
def list_compliance_documents(
    category: str | None = Query(default=None, max_length=64),
    document_status: ComplianceDocumentStatus | None = Query(
        default=None, alias="status"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: dict[str, Any] = Depends(
        require_roles(*_READ_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[list[ComplianceDocumentResponse]]:
    documents = service.list_documents(
        category=category,
        status_filter=document_status,
        limit=limit,
        offset=offset,
    )
    return APIResponse(
        success=True,
        message="Compliance documents retrieved successfully.",
        data=[ComplianceDocumentResponse.model_validate(row) for row in documents],
    )


@router.get(
    "/{document_id}",
    response_model=APIResponse[ComplianceDocumentResponse],
    summary="Get a compliance document",
)
def get_compliance_document(
    document_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(*_READ_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceDocumentResponse]:
    document = service.get_document(document_id)
    return APIResponse(
        success=True,
        message="Compliance document retrieved successfully.",
        data=ComplianceDocumentResponse.model_validate(document),
    )


@router.get(
    "/{document_id}/versions",
    response_model=APIResponse[list[ComplianceDocumentVersionResponse]],
    summary="List immutable document versions",
)
def list_compliance_document_versions(
    document_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(*_READ_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[list[ComplianceDocumentVersionResponse]]:
    versions = service.list_versions(document_id)
    return APIResponse(
        success=True,
        message="Compliance document versions retrieved successfully.",
        data=[
            ComplianceDocumentVersionResponse.model_validate(row) for row in versions
        ],
    )


@router.post(
    "/{document_id}/versions",
    response_model=APIResponse[ComplianceDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document version",
)
async def create_compliance_document_version(
    document_id: UUID,
    file: UploadFile = File(...),
    change_summary: str | None = Form(default=None, max_length=2000),
    _: dict[str, Any] = Depends(
        require_roles(*_WRITE_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceDocumentResponse]:
    document = await service.create_version(
        document_id=document_id,
        file=file,
        change_summary=change_summary,
    )
    return APIResponse(
        success=True,
        message="New immutable document version uploaded.",
        data=ComplianceDocumentResponse.model_validate(document),
    )


@router.get(
    "/{document_id}/versions/{version_number}/download",
    summary="Download a stored document version",
)
def download_compliance_document_version(
    request: Request,
    document_id: UUID,
    version_number: int,
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_user),
    _: dict[str, Any] = Depends(
        require_roles(*_READ_ROLES, resource_type="compliance_document")
    ),
) -> Response:
    versions = service.list_versions(document_id)
    selected = next((item for item in versions if item.version == version_number), None)
    if selected is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail="Compliance document version not found.",
        )
    content, filename, content_type = file_service.download_file(
        file_id=selected.file_id,
        user_id=current_user.id,
        email=str(current_user.email),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    safe_filename = filename.replace("\r", "").replace("\n", "").replace('"', "")
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@router.post(
    "/{document_id}/submit-for-approval",
    response_model=APIResponse[ComplianceDocumentResponse],
    summary="Submit current version for approval",
)
def submit_compliance_document_for_approval(
    document_id: UUID,
    payload: ComplianceApprovalComment,
    _: dict[str, Any] = Depends(
        require_roles(*_WRITE_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceDocumentResponse]:
    document = service.submit_for_approval(document_id, payload.comment)
    return APIResponse(
        success=True,
        message="Document submitted for approval.",
        data=ComplianceDocumentResponse.model_validate(document),
    )


@router.post(
    "/{document_id}/approve",
    response_model=APIResponse[ComplianceDocumentResponse],
    summary="Approve the current submitted version",
)
def approve_compliance_document(
    document_id: UUID,
    payload: ComplianceApprovalComment,
    _: dict[str, Any] = Depends(
        require_roles(*_APPROVER_ROLES, resource_type="compliance_document_approval")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceDocumentResponse]:
    document = service.approve(document_id, payload.comment)
    return APIResponse(
        success=True,
        message="Compliance document approved.",
        data=ComplianceDocumentResponse.model_validate(document),
    )


@router.post(
    "/{document_id}/reject",
    response_model=APIResponse[ComplianceDocumentResponse],
    summary="Reject the current submitted version",
)
def reject_compliance_document(
    document_id: UUID,
    payload: ComplianceApprovalComment,
    _: dict[str, Any] = Depends(
        require_roles(*_APPROVER_ROLES, resource_type="compliance_document_approval")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceDocumentResponse]:
    document = service.reject(document_id, payload.comment)
    return APIResponse(
        success=True,
        message="Compliance document rejected.",
        data=ComplianceDocumentResponse.model_validate(document),
    )


@router.get(
    "/{document_id}/approvals",
    response_model=APIResponse[list[ComplianceApprovalResponse]],
    summary="List approval history",
)
def list_compliance_document_approvals(
    document_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(*_READ_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[list[ComplianceApprovalResponse]]:
    approvals = service.list_approvals(document_id)
    return APIResponse(
        success=True,
        message="Approval history retrieved successfully.",
        data=[ComplianceApprovalResponse.model_validate(row) for row in approvals],
    )


@router.post(
    "/{document_id}/evidence",
    response_model=APIResponse[ComplianceEvidenceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record evidence associated with a document",
)
def add_compliance_evidence(
    document_id: UUID,
    payload: ComplianceEvidenceCreate,
    _: dict[str, Any] = Depends(
        require_roles(*_WRITE_ROLES, resource_type="compliance_evidence")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceEvidenceResponse]:
    evidence = service.add_evidence(
        document_id,
        payload,
        allowed_evidence_types=_EVIDENCE_TYPES,
    )
    return APIResponse(
        success=True,
        message="Evidence record created.",
        data=ComplianceEvidenceResponse.model_validate(evidence),
    )


@router.get(
    "/{document_id}/evidence",
    response_model=APIResponse[list[ComplianceEvidenceResponse]],
    summary="List evidence records for a document",
)
def list_compliance_evidence(
    document_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(*_READ_ROLES, resource_type="compliance_evidence")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[list[ComplianceEvidenceResponse]]:
    evidence = service.list_evidence(document_id)
    return APIResponse(
        success=True,
        message="Compliance evidence retrieved successfully.",
        data=[ComplianceEvidenceResponse.model_validate(row) for row in evidence],
    )


@router.patch(
    "/{document_id}/archive",
    response_model=APIResponse[ComplianceDocumentResponse],
    summary="Archive a document",
)
def archive_compliance_document(
    document_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(*_APPROVER_ROLES, resource_type="compliance_document")
    ),
    service: ComplianceDocumentService = Depends(get_compliance_document_service),
) -> APIResponse[ComplianceDocumentResponse]:
    document = service.archive(document_id)
    return APIResponse(
        success=True,
        message="Compliance document archived.",
        data=ComplianceDocumentResponse.model_validate(document),
    )
