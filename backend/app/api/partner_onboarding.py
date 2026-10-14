"""Public partner onboarding submission and platform-admin review APIs."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_platform_admin
from app.schemas.partner_onboarding import (
    PartnerBusinessInformationUpdate,
    PartnerOnboardingAction,
    PartnerOnboardingAssignment,
    PartnerOnboardingCreate,
    PartnerOnboardingHistoryResponse,
    PartnerOnboardingReject,
    PartnerOnboardingResponse,
)
from app.services.partner_onboarding_service import PartnerOnboardingService
from app.utils.enums import PartnerOnboardingStatus

router = APIRouter(
    prefix="/api/v1/partner-onboarding",
    tags=["Partner Onboarding"],
)


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def _actor_arguments(
    request: Request,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    ip_address, user_agent = _metadata(request)
    return {
        "actor_id": UUID(current_user["sub"]),
        "actor_email": current_user["email"],
        "ip_address": ip_address,
        "user_agent": user_agent,
    }


@router.post(
    "",
    response_model=APIResponse[PartnerOnboardingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a partner onboarding request",
    description=(
        "Public endpoint for a prospective bank or fintech to submit its business "
        "information. Review, assignment, and activation require platform-admin access."
    ),
)
def create_partner_request(
    payload: PartnerOnboardingCreate,
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = PartnerOnboardingService(db).create_request(payload)
    return APIResponse(
        success=True,
        message="Partner onboarding request submitted successfully.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.get(
    "",
    response_model=APIResponse[list[PartnerOnboardingResponse]],
    summary="List partner onboarding requests",
)
def list_partner_requests(
    onboarding_status: PartnerOnboardingStatus | None = Query(
        default=None, alias="status"
    ),
    assigned_to: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[list[PartnerOnboardingResponse]]:
    requests = PartnerOnboardingService(db).list_requests(
        status=onboarding_status,
        assigned_to=assigned_to,
    )
    return APIResponse(
        success=True,
        message="Partner onboarding requests retrieved successfully.",
        data=[PartnerOnboardingResponse.model_validate(item) for item in requests],
    )


@router.get(
    "/{onboarding_id}",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Get partner onboarding request",
)
def get_partner_request(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = PartnerOnboardingService(db).get_request(onboarding_id)
    return APIResponse(
        success=True,
        message="Partner onboarding request retrieved successfully.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.put(
    "/{onboarding_id}/business-information",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Update partner business information",
)
def update_business_information(
    onboarding_id: UUID,
    payload: PartnerBusinessInformationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = PartnerOnboardingService(db).update_business_information(
        onboarding_id=onboarding_id,
        data=payload,
        **_actor_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message="Partner business information updated successfully.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.patch(
    "/{onboarding_id}/assignment",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Assign an internal reviewer",
)
def assign_partner_reviewer(
    onboarding_id: UUID,
    payload: PartnerOnboardingAssignment,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = PartnerOnboardingService(db).assign_reviewer(
        onboarding_id=onboarding_id,
        assigned_to=payload.assigned_to,
        **_actor_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message="Partner onboarding reviewer assigned successfully.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.post(
    "/{onboarding_id}/advance",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Advance partner onboarding to the next workflow stage",
)
def advance_partner_stage(
    onboarding_id: UUID,
    payload: PartnerOnboardingAction,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = PartnerOnboardingService(db).advance_stage(
        onboarding_id=onboarding_id,
        notes=payload.notes,
        **_actor_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message=f"Partner onboarding advanced to {onboarding.status.value}.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.post(
    "/{onboarding_id}/approve",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Approve and activate a partner",
)
def approve_partner(
    onboarding_id: UUID,
    payload: PartnerOnboardingAction,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = PartnerOnboardingService(db).approve_and_activate(
        onboarding_id=onboarding_id,
        notes=payload.notes,
        **_actor_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message="Partner approved; tenant and organization activated successfully.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.post(
    "/{onboarding_id}/reject",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Reject a partner onboarding request",
)
def reject_partner(
    onboarding_id: UUID,
    payload: PartnerOnboardingReject,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = PartnerOnboardingService(db).reject(
        onboarding_id=onboarding_id,
        reason=payload.reason,
        **_actor_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message="Partner onboarding request rejected.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.get(
    "/{onboarding_id}/history",
    response_model=APIResponse[list[PartnerOnboardingHistoryResponse]],
    summary="Get partner onboarding history",
)
def get_partner_history(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[list[PartnerOnboardingHistoryResponse]]:
    history = PartnerOnboardingService(db).get_history(onboarding_id)
    return APIResponse(
        success=True,
        message="Partner onboarding history retrieved successfully.",
        data=[
            PartnerOnboardingHistoryResponse.model_validate(item) for item in history
        ],
    )
