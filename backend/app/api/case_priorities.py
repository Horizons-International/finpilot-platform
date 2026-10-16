from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.case_priority import CasePriorityResponse
from app.services.case_priority_service import CasePriorityService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/case-priorities", tags=["Case Priorities"])

_ALLOWED_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
)


@router.get(
    "",
    response_model=APIResponse[list[CasePriorityResponse]],
    summary="List prioritized open compliance cases",
    description=(
        "Refreshes priorities from the latest tenant-scoped risk inputs and "
        "returns open cases ordered by priority score."
    ),
)
def list_case_priorities(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(require_roles(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> APIResponse[list[CasePriorityResponse]]:
    service = CasePriorityService(db, tenant_id=UUID(current_user["tenant_id"]))
    priorities = service.list_open_case_priorities(limit=limit)
    return APIResponse(
        success=True,
        message="Compliance case priorities retrieved successfully.",
        data=[CasePriorityResponse.model_validate(item) for item in priorities],
    )


@router.get(
    "/{case_id}",
    response_model=APIResponse[CasePriorityResponse],
    summary="Get latest priority for a compliance case",
)
def get_case_priority(
    case_id: UUID,
    current_user: dict[str, Any] = Depends(require_roles(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> APIResponse[CasePriorityResponse]:
    service = CasePriorityService(db, tenant_id=UUID(current_user["tenant_id"]))
    priority = service.prioritize_case(case_id)
    return APIResponse(
        success=True,
        message="Compliance case priority retrieved successfully.",
        data=CasePriorityResponse.model_validate(priority),
    )


@router.post(
    "/{case_id}/recalculate",
    response_model=APIResponse[CasePriorityResponse],
    status_code=status.HTTP_200_OK,
    summary="Recalculate compliance case priority",
    description=(
        "Recalculates the explainable score and stores a new history row "
        "when inputs changed."
    ),
)
def recalculate_case_priority(
    case_id: UUID,
    current_user: dict[str, Any] = Depends(require_roles(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> APIResponse[CasePriorityResponse]:
    service = CasePriorityService(db, tenant_id=UUID(current_user["tenant_id"]))
    priority = service.prioritize_case(case_id)
    return APIResponse(
        success=True,
        message="Compliance case priority recalculated successfully.",
        data=CasePriorityResponse.model_validate(priority),
    )


@router.get(
    "/{case_id}/history",
    response_model=APIResponse[list[CasePriorityResponse]],
    summary="Get priority history for a compliance case",
)
def get_case_priority_history(
    case_id: UUID,
    current_user: dict[str, Any] = Depends(require_roles(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> APIResponse[list[CasePriorityResponse]]:
    service = CasePriorityService(db, tenant_id=UUID(current_user["tenant_id"]))
    history = service.get_history(case_id)
    return APIResponse(
        success=True,
        message="Compliance case priority history retrieved successfully.",
        data=[CasePriorityResponse.model_validate(item) for item in history],
    )
