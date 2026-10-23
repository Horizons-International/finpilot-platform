"""Public self-service partner onboarding and platform-admin review APIs."""

from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Header,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi import (
    File as FastAPIFile,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_platform_admin
from app.schemas.partner_onboarding import (
    PartnerBusinessInformationUpdate,
    PartnerOnboardingAction,
    PartnerOnboardingActivationResponse,
    PartnerOnboardingAdministratorCreate,
    PartnerOnboardingAdministratorCreatedResponse,
    PartnerOnboardingAdministratorResponse,
    PartnerOnboardingAssignment,
    PartnerOnboardingCreate,
    PartnerOnboardingDocumentResponse,
    PartnerOnboardingDocumentReview,
    PartnerOnboardingHistoryResponse,
    PartnerOnboardingPortalCreatedResponse,
    PartnerOnboardingPortalSubmitResponse,
    PartnerOnboardingProgressResponse,
    PartnerOnboardingReject,
    PartnerOnboardingResponse,
    PartnerTechnicalSetupUpdate,
)
from app.services.partner_onboarding_portal_service import (
    PartnerOnboardingPortalService,
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


# ---------------------------------------------------------------------------
# Existing platform-managed onboarding endpoints (backward compatible)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=APIResponse[PartnerOnboardingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a platform-managed partner onboarding request",
    description=(
        "Compatibility endpoint for the existing onboarding queue. New self-service "
        "customer portals should use POST /api/v1/partner-onboarding/portal."
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


@router.get(
    "/{onboarding_id}/progress",
    response_model=APIResponse[PartnerOnboardingProgressResponse],
    summary="View onboarding progress for internal review",
)
def get_internal_partner_progress(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingProgressResponse]:
    progress = PartnerOnboardingPortalService(db).get_internal_progress(onboarding_id)
    return APIResponse(
        success=True,
        message="Partner onboarding progress retrieved successfully.",
        data=progress,
    )


@router.put(
    "/{onboarding_id}/business-information",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Update partner business information as platform staff",
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
    service = PartnerOnboardingService(db)
    onboarding = service.get_request(onboarding_id)
    if onboarding.portal_token_hash:
        PartnerOnboardingPortalService(db).ensure_can_advance(onboarding_id)
    onboarding = service.advance_stage(
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
    response_model=APIResponse[PartnerOnboardingActivationResponse],
    summary="Approve and activate a partner",
)
def approve_partner(
    onboarding_id: UUID,
    payload: PartnerOnboardingAction,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingActivationResponse]:
    service = PartnerOnboardingService(db)
    current = service.get_request(onboarding_id)
    actor = _actor_arguments(request, current_user)
    if current.portal_token_hash:
        onboarding, raw_api_key = PartnerOnboardingPortalService(
            db
        ).activate_and_issue_credentials(
            onboarding_id=onboarding_id,
            notes=payload.notes,
            **actor,
        )
    else:
        onboarding = service.approve_and_activate(
            onboarding_id=onboarding_id,
            notes=payload.notes,
            **actor,
        )
        raw_api_key = None
    response_data = PartnerOnboardingActivationResponse(
        **PartnerOnboardingResponse.model_validate(onboarding).model_dump(),
        api_key=raw_api_key,
    )
    return APIResponse(
        success=True,
        message=(
            "Partner approved and activated. The initial API key is shown only in "
            "this response; copy it to a secure secret store."
            if raw_api_key
            else "Partner approved; tenant and organization activated successfully."
        ),
        data=response_data,
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


@router.get(
    "/{onboarding_id}/documents",
    response_model=APIResponse[list[PartnerOnboardingDocumentResponse]],
    summary="List onboarding evidence for internal review",
)
def list_onboarding_documents(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[list[PartnerOnboardingDocumentResponse]]:
    progress = PartnerOnboardingPortalService(db).get_internal_progress(onboarding_id)
    return APIResponse(
        success=True,
        message="Partner onboarding documents retrieved successfully.",
        data=progress.documents,
    )


@router.get(
    "/{onboarding_id}/documents/{document_id}/download",
    summary="Download onboarding evidence for internal review",
)
def download_onboarding_document(
    onboarding_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> Response:
    path, document = PartnerOnboardingPortalService(db).document_storage_path(
        onboarding_id, document_id
    )
    safe_name = (
        document.original_filename.replace('"', "'").replace("\r", "").replace("\n", "")
    )
    return Response(
        content=path.read_bytes(),
        media_type=document.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{quote(safe_name, safe="")}"'
            )
        },
    )


@router.patch(
    "/{onboarding_id}/documents/{document_id}/review",
    response_model=APIResponse[PartnerOnboardingDocumentResponse],
    summary="Approve or reject an onboarding document",
)
def review_onboarding_document(
    onboarding_id: UUID,
    document_id: UUID,
    payload: PartnerOnboardingDocumentReview,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[PartnerOnboardingDocumentResponse]:
    document = PartnerOnboardingPortalService(db).review_document(
        onboarding_id=onboarding_id,
        document_id=document_id,
        review_status=payload.review_status,
        notes=payload.notes,
        **_actor_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message=f"Onboarding document marked {document.review_status.lower()}.",
        data=PartnerOnboardingDocumentResponse.model_validate(document),
    )


# ---------------------------------------------------------------------------
# Self-service customer portal. These routes use X-Onboarding-Token rather than
# a user JWT because the prospective bank does not have a tenant/user account yet.
# ---------------------------------------------------------------------------


@router.post(
    "/portal",
    response_model=APIResponse[PartnerOnboardingPortalCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a self-service onboarding portal for a bank",
)
def create_onboarding_portal(
    payload: PartnerOnboardingCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingPortalCreatedResponse]:
    ip_address, user_agent = _metadata(request)
    onboarding, portal_token = PartnerOnboardingPortalService(db).create_portal_request(
        payload, ip_address=ip_address, user_agent=user_agent
    )
    token_expires_at = onboarding.portal_token_expires_at
    if token_expires_at is None:
        raise RuntimeError("Portal token expiry was not set during request creation.")
    data = PartnerOnboardingPortalCreatedResponse(
        **PartnerOnboardingResponse.model_validate(onboarding).model_dump(),
        portal_token=portal_token,
        portal_token_expires_at=token_expires_at,
    )
    return APIResponse(
        success=True,
        message=(
            "Onboarding portal created. Save the portal token securely; it is shown "
            "only in this response."
        ),
        data=data,
    )


@router.get(
    "/portal/{onboarding_id}/progress",
    response_model=APIResponse[PartnerOnboardingProgressResponse],
    summary="View onboarding progress from the customer portal",
)
def get_portal_progress(
    onboarding_id: UUID,
    token: str = Header(alias="X-Onboarding-Token"),
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingProgressResponse]:
    progress = PartnerOnboardingPortalService(db).get_portal_progress(
        onboarding_id, token=token
    )
    return APIResponse(
        success=True,
        message="Onboarding progress retrieved successfully.",
        data=progress,
    )


@router.patch(
    "/portal/{onboarding_id}/business-information",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Update company business information from the customer portal",
)
def update_portal_business_information(
    onboarding_id: UUID,
    payload: PartnerBusinessInformationUpdate,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingResponse]:
    ip_address, user_agent = _metadata(request)
    onboarding = PartnerOnboardingPortalService(db).update_business_information(
        onboarding_id=onboarding_id,
        token=token,
        data=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Business information updated successfully.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.post(
    "/portal/{onboarding_id}/administrators",
    response_model=APIResponse[PartnerOnboardingAdministratorCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Nominate an organization administrator",
)
def add_portal_administrator(
    onboarding_id: UUID,
    payload: PartnerOnboardingAdministratorCreate,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingAdministratorCreatedResponse]:
    ip_address, user_agent = _metadata(request)
    administrator, invitation_token = PartnerOnboardingPortalService(
        db
    ).add_administrator(
        onboarding_id=onboarding_id,
        token=token,
        data=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    data = PartnerOnboardingAdministratorCreatedResponse(
        **PartnerOnboardingAdministratorResponse.model_validate(
            administrator
        ).model_dump(),
        invitation_token=invitation_token,
    )
    return APIResponse(
        success=True,
        message=(
            "Administrator nominated. Save the invitation token; it becomes usable "
            "after the organization is activated."
        ),
        data=data,
    )


@router.post(
    "/portal/{onboarding_id}/documents",
    response_model=APIResponse[PartnerOnboardingDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit an onboarding document",
)
async def upload_portal_document(
    onboarding_id: UUID,
    request: Request,
    document_type: str = Form(...),
    file: UploadFile = FastAPIFile(...),
    token: str = Header(alias="X-Onboarding-Token"),
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingDocumentResponse]:
    ip_address, user_agent = _metadata(request)
    document = await PartnerOnboardingPortalService(db).upload_document(
        onboarding_id=onboarding_id,
        token=token,
        document_type=document_type,
        file=file,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Onboarding document uploaded successfully.",
        data=PartnerOnboardingDocumentResponse.model_validate(document),
    )


@router.put(
    "/portal/{onboarding_id}/technical-setup",
    response_model=APIResponse[PartnerOnboardingResponse],
    summary="Save technical integration setup",
)
def update_portal_technical_setup(
    onboarding_id: UUID,
    payload: PartnerTechnicalSetupUpdate,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingResponse]:
    ip_address, user_agent = _metadata(request)
    onboarding = PartnerOnboardingPortalService(db).save_technical_setup(
        onboarding_id=onboarding_id,
        token=token,
        data=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Technical setup saved successfully.",
        data=PartnerOnboardingResponse.model_validate(onboarding),
    )


@router.post(
    "/portal/{onboarding_id}/submit",
    response_model=APIResponse[PartnerOnboardingPortalSubmitResponse],
    summary="Submit onboarding for internal review",
)
def submit_portal_onboarding(
    onboarding_id: UUID,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: Session = Depends(get_db),
) -> APIResponse[PartnerOnboardingPortalSubmitResponse]:
    ip_address, user_agent = _metadata(request)
    service = PartnerOnboardingPortalService(db)
    onboarding = service.submit_for_review(
        onboarding_id=onboarding_id,
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    progress = service.get_portal_progress(onboarding_id, token=token)
    return APIResponse(
        success=True,
        message="Onboarding submitted for internal review.",
        data=PartnerOnboardingPortalSubmitResponse(
            onboarding_id=onboarding.id,
            status=onboarding.status,
            submitted=True,
            progress_percent=progress.progress_percent,
        ),
    )
