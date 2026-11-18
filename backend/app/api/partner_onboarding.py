"""Public self-service partner onboarding and platform-admin review APIs.

Database-backed writes use AsyncSession. File download remains synchronous because
it reads a local storage path; document upload continues to use its dedicated async
service, which moves blocking filesystem I/O to the thread pool.
"""

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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.async_security import require_async_platform_admin
from app.core.database import get_async_db, get_db
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
from app.services.async_partner_onboarding_document_service import (
    AsyncPartnerOnboardingDocumentService,
)
from app.services.async_partner_onboarding_read_service import (
    AsyncPartnerOnboardingReadService,
)
from app.services.async_partner_onboarding_write_service import (
    AsyncPartnerOnboardingPortalWriteService,
    AsyncPartnerOnboardingWriteService,
)
from app.services.partner_onboarding_portal_service import (
    PartnerOnboardingPortalService,
)
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
# Platform-managed onboarding queue
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
async def create_partner_request(
    payload: PartnerOnboardingCreate,
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = await AsyncPartnerOnboardingWriteService(db).create_request(payload)
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
async def list_partner_requests(
    onboarding_status: PartnerOnboardingStatus | None = Query(
        default=None, alias="status"
    ),
    assigned_to: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[list[PartnerOnboardingResponse]]:
    requests = await AsyncPartnerOnboardingReadService(db).list_requests(
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
async def get_partner_request(
    onboarding_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = await AsyncPartnerOnboardingReadService(db).get_request(onboarding_id)
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
async def get_internal_partner_progress(
    onboarding_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingProgressResponse]:
    progress = await AsyncPartnerOnboardingReadService(db).get_internal_progress(
        onboarding_id
    )
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
async def update_business_information(
    onboarding_id: UUID,
    payload: PartnerBusinessInformationUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = await AsyncPartnerOnboardingWriteService(
        db
    ).update_business_information(
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
async def assign_partner_reviewer(
    onboarding_id: UUID,
    payload: PartnerOnboardingAssignment,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = await AsyncPartnerOnboardingWriteService(db).assign_reviewer(
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
async def advance_partner_stage(
    onboarding_id: UUID,
    payload: PartnerOnboardingAction,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = await AsyncPartnerOnboardingWriteService(db).advance_stage(
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
async def approve_partner(
    onboarding_id: UUID,
    payload: PartnerOnboardingAction,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingActivationResponse]:
    service = AsyncPartnerOnboardingWriteService(db)
    current = await service.get_request(onboarding_id)
    actor = _actor_arguments(request, current_user)
    if current.portal_token_hash:
        onboarding, raw_api_key = await AsyncPartnerOnboardingPortalWriteService(
            db
        ).activate_and_issue_credentials(
            onboarding_id=onboarding_id,
            notes=payload.notes,
            **actor,
        )
    else:
        onboarding = await service.approve_and_activate(
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
async def reject_partner(
    onboarding_id: UUID,
    payload: PartnerOnboardingReject,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingResponse]:
    onboarding = await AsyncPartnerOnboardingWriteService(db).reject(
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
async def get_partner_history(
    onboarding_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[list[PartnerOnboardingHistoryResponse]]:
    history = await AsyncPartnerOnboardingReadService(db).get_history(onboarding_id)
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
async def list_onboarding_documents(
    onboarding_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[list[PartnerOnboardingDocumentResponse]]:
    documents = await AsyncPartnerOnboardingReadService(db).list_documents(
        onboarding_id
    )
    return APIResponse(
        success=True,
        message="Partner onboarding documents retrieved successfully.",
        data=[
            PartnerOnboardingDocumentResponse.model_validate(item) for item in documents
        ],
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
    # Keep file I/O in the synchronous route; no AsyncSession is involved here.
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
async def review_onboarding_document(
    onboarding_id: UUID,
    document_id: UUID,
    payload: PartnerOnboardingDocumentReview,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[PartnerOnboardingDocumentResponse]:
    document = await AsyncPartnerOnboardingPortalWriteService(db).review_document(
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
# Self-service portal. These endpoints use X-Onboarding-Token rather than a JWT.
# ---------------------------------------------------------------------------


@router.post(
    "/portal",
    response_model=APIResponse[PartnerOnboardingPortalCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a self-service onboarding portal for a bank",
)
async def create_onboarding_portal(
    payload: PartnerOnboardingCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingPortalCreatedResponse]:
    ip_address, user_agent = _metadata(request)
    onboarding, portal_token = await AsyncPartnerOnboardingPortalWriteService(
        db
    ).create_portal_request(payload, ip_address=ip_address, user_agent=user_agent)
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
async def get_portal_progress(
    onboarding_id: UUID,
    token: str = Header(alias="X-Onboarding-Token"),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingProgressResponse]:
    progress = await AsyncPartnerOnboardingReadService(db).get_portal_progress(
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
async def update_portal_business_information(
    onboarding_id: UUID,
    payload: PartnerBusinessInformationUpdate,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingResponse]:
    ip_address, user_agent = _metadata(request)
    onboarding = await AsyncPartnerOnboardingPortalWriteService(
        db
    ).update_business_information_with_portal_token(
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
async def add_portal_administrator(
    onboarding_id: UUID,
    payload: PartnerOnboardingAdministratorCreate,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingAdministratorCreatedResponse]:
    ip_address, user_agent = _metadata(request)
    administrator, invitation_token = await AsyncPartnerOnboardingPortalWriteService(
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
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingDocumentResponse]:
    ip_address, user_agent = _metadata(request)
    document = await AsyncPartnerOnboardingDocumentService(db).upload_document(
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
async def update_portal_technical_setup(
    onboarding_id: UUID,
    payload: PartnerTechnicalSetupUpdate,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingResponse]:
    ip_address, user_agent = _metadata(request)
    onboarding = await AsyncPartnerOnboardingPortalWriteService(
        db
    ).save_technical_setup(
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
async def submit_portal_onboarding(
    onboarding_id: UUID,
    request: Request,
    token: str = Header(alias="X-Onboarding-Token"),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[PartnerOnboardingPortalSubmitResponse]:
    ip_address, user_agent = _metadata(request)
    service = AsyncPartnerOnboardingPortalWriteService(db)
    onboarding = await service.submit_for_review(
        onboarding_id=onboarding_id,
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    progress = await AsyncPartnerOnboardingReadService(db).get_portal_progress(
        onboarding_id, token=token
    )
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
