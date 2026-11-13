"""Native-async tenant API for webhook subscriptions and delivery history."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreatedResponse,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookStatusUpdate,
    WebhookUpdate,
)
from app.services.async_platform_integration_service import AsyncWebhookService
from app.utils.enums import UserRole, WebhookDeliveryStatus, WebhookStatus

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


def _service(db: AsyncSession, current_user: dict[str, Any]) -> AsyncWebhookService:
    return AsyncWebhookService(db, UUID(current_user["tenant_id"]))


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
async def create_webhook(
    payload: WebhookCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[WebhookCreatedResponse]:
    ip, agent = _metadata(request)
    webhook, secret = await _service(db, current_user).create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Webhook registered successfully. Store the signing secret securely.",
        data=WebhookCreatedResponse(
            webhook=WebhookResponse.model_validate(webhook), signing_secret=secret
        ),
    )


@router.get(
    "",
    response_model=APIResponse[list[WebhookResponse]],
    summary="List webhook subscriptions",
)
async def list_webhooks(
    webhook_status: WebhookStatus | None = Query(default=None, alias="status"),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[WebhookResponse]]:
    rows = await _service(db, current_user).list_all(status=webhook_status)
    return APIResponse(
        success=True,
        message="Webhooks retrieved successfully.",
        data=[WebhookResponse.model_validate(row) for row in rows],
    )


@router.get(
    "/{webhook_id}",
    response_model=APIResponse[WebhookResponse],
    summary="Get webhook subscription",
)
async def get_webhook(
    webhook_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[WebhookResponse]:
    row = await _service(db, current_user).get_by_id(webhook_id)
    return APIResponse(
        success=True,
        message="Webhook retrieved successfully.",
        data=WebhookResponse.model_validate(row),
    )


@router.patch(
    "/{webhook_id}",
    response_model=APIResponse[WebhookResponse],
    summary="Update webhook endpoint or event subscriptions",
)
async def update_webhook(
    webhook_id: UUID,
    payload: WebhookUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[WebhookResponse]:
    ip, agent = _metadata(request)
    row = await _service(db, current_user).update(
        webhook_id=webhook_id,
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Webhook updated successfully.",
        data=WebhookResponse.model_validate(row),
    )


@router.patch(
    "/{webhook_id}/status",
    response_model=APIResponse[WebhookResponse],
    summary="Enable or disable a webhook subscription",
)
async def update_webhook_status(
    webhook_id: UUID,
    payload: WebhookStatusUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[WebhookResponse]:
    ip, agent = _metadata(request)
    row = await _service(db, current_user).set_status(
        webhook_id=webhook_id,
        status=payload.status,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Webhook status updated successfully.",
        data=WebhookResponse.model_validate(row),
    )


@router.get(
    "/{webhook_id}/deliveries",
    response_model=APIResponse[list[WebhookDeliveryResponse]],
    summary="List webhook delivery history",
)
async def list_webhook_deliveries(
    webhook_id: UUID,
    delivery_status: WebhookDeliveryStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="webhook")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[WebhookDeliveryResponse]]:
    rows = await _service(db, current_user).list_deliveries(
        webhook_id, status=delivery_status, limit=limit
    )
    return APIResponse(
        success=True,
        message="Webhook delivery history retrieved successfully.",
        data=[WebhookDeliveryResponse.model_validate(row) for row in rows],
    )
