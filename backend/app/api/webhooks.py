"""Tenant-administrator API for managing webhook subscriptions and history."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreatedResponse,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookStatusUpdate,
    WebhookUpdate,
)
from app.services.webhook_service import WebhookService
from app.utils.enums import UserRole, WebhookDeliveryStatus, WebhookStatus

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


def get_webhook_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookService:
    return WebhookService(db=db, tenant_id=current_user.tenant_id)


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def _audit_actor(current_user: dict[str, Any]) -> tuple[UUID, str]:
    return UUID(current_user["sub"]), current_user["email"]


@router.post(
    "",
    response_model=APIResponse[WebhookCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register webhook endpoint",
    description=(
        "Creates a webhook subscription. The signing secret is returned only "
        "once; save it securely to verify X-FinPilot-Signature headers."
    ),
)
def create_webhook(
    payload: WebhookCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    service: WebhookService = Depends(get_webhook_service),
) -> APIResponse[WebhookCreatedResponse]:
    user_id, email = _audit_actor(current_user)
    ip_address, user_agent = _metadata(request)
    webhook, secret = service.create(
        data=payload,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Webhook registered successfully. Store the signing secret securely.",
        data=WebhookCreatedResponse(
            webhook=WebhookResponse.model_validate(webhook),
            signing_secret=secret,
        ),
    )


@router.get(
    "",
    response_model=APIResponse[list[WebhookResponse]],
    summary="List webhook subscriptions",
)
def list_webhooks(
    webhook_status: WebhookStatus | None = Query(default=None, alias="status"),
    _: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    service: WebhookService = Depends(get_webhook_service),
) -> APIResponse[list[WebhookResponse]]:
    hooks = service.list_all(status=webhook_status)
    return APIResponse(
        success=True,
        message="Webhooks retrieved successfully.",
        data=[WebhookResponse.model_validate(item) for item in hooks],
    )


@router.get(
    "/{webhook_id}",
    response_model=APIResponse[WebhookResponse],
    summary="Get webhook subscription",
)
def get_webhook(
    webhook_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    service: WebhookService = Depends(get_webhook_service),
) -> APIResponse[WebhookResponse]:
    webhook = service.get_by_id(webhook_id)
    return APIResponse(
        success=True,
        message="Webhook retrieved successfully.",
        data=WebhookResponse.model_validate(webhook),
    )


@router.patch(
    "/{webhook_id}",
    response_model=APIResponse[WebhookResponse],
    summary="Update webhook endpoint or event subscriptions",
)
def update_webhook(
    webhook_id: UUID,
    payload: WebhookUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    service: WebhookService = Depends(get_webhook_service),
) -> APIResponse[WebhookResponse]:
    user_id, email = _audit_actor(current_user)
    ip_address, user_agent = _metadata(request)
    webhook = service.update(
        webhook_id=webhook_id,
        data=payload,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Webhook updated successfully.",
        data=WebhookResponse.model_validate(webhook),
    )


@router.patch(
    "/{webhook_id}/status",
    response_model=APIResponse[WebhookResponse],
    summary="Enable or disable a webhook subscription",
)
def update_webhook_status(
    webhook_id: UUID,
    payload: WebhookStatusUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    service: WebhookService = Depends(get_webhook_service),
) -> APIResponse[WebhookResponse]:
    user_id, email = _audit_actor(current_user)
    ip_address, user_agent = _metadata(request)
    webhook = service.set_status(
        webhook_id=webhook_id,
        status=payload.status,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Webhook status updated successfully.",
        data=WebhookResponse.model_validate(webhook),
    )


@router.get(
    "/{webhook_id}/deliveries",
    response_model=APIResponse[list[WebhookDeliveryResponse]],
    summary="List webhook delivery history",
)
def list_webhook_deliveries(
    webhook_id: UUID,
    delivery_status: WebhookDeliveryStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    _: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    service: WebhookService = Depends(get_webhook_service),
) -> APIResponse[list[WebhookDeliveryResponse]]:
    deliveries = service.list_deliveries(
        webhook_id,
        status=delivery_status,
        limit=limit,
    )
    return APIResponse(
        success=True,
        message="Webhook delivery history retrieved successfully.",
        data=[WebhookDeliveryResponse.model_validate(item) for item in deliveries],
    )
