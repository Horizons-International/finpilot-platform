"""Customer feedback intake, status tracking and product roadmap management."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer_feedback import (
    CustomerFeedbackCreate,
    CustomerFeedbackHistoryResponse,
    CustomerFeedbackResponse,
    CustomerFeedbackSummaryResponse,
    CustomerFeedbackUpdate,
    FeedbackCategory,
    FeedbackPriority,
    FeedbackStatus,
    ProductRoadmapItemCreate,
    ProductRoadmapItemResponse,
    ProductRoadmapItemUpdate,
)
from app.services.async_customer_feedback_service import AsyncCustomerFeedbackService
from app.utils.enums import UserRole
from app.utils.errors import forbidden

router = APIRouter(
    prefix="/api/v1/customer-feedback",
    tags=["Customer Feedback"],
)

_CUSTOMER_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.ANALYST,
    UserRole.VIEWER,
    UserRole.AUDITOR,
)


def _service(
    db: AsyncSession, current_user: dict[str, Any]
) -> AsyncCustomerFeedbackService:
    return AsyncCustomerFeedbackService(db, tenant_id=UUID(current_user["tenant_id"]))


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(current_user["sub"])


def _require_product_manager(
    context: dict[str, Any] = Depends(
        require_async_roles(UserRole.PRODUCT_MANAGER, resource_type="customer-feedback")
    ),
) -> dict[str, Any]:
    # Role is necessary but not sufficient: cross-tenant product access requires
    # the trusted platform-admin flag used throughout FinPilot for global actions.
    if not context.get("is_platform_admin", False):
        raise forbidden(
            "Product-wide feedback access requires an authorized "
            "platform product manager."
        )
    return context


@router.post(
    "",
    response_model=APIResponse[CustomerFeedbackResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback for the current bank tenant",
)
async def submit_feedback(
    payload: CustomerFeedbackCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_ROLES, resource_type="customer-feedback")
    ),
) -> APIResponse[CustomerFeedbackResponse]:
    service = _service(db, current_user)
    feedback = await service.create_feedback(payload, actor_id=_actor_id(current_user))
    return APIResponse(
        success=True,
        message="Customer feedback submitted successfully.",
        data=CustomerFeedbackResponse.model_validate(
            service.serialize_feedback(feedback)
        ),
    )


@router.get(
    "",
    response_model=APIResponse[list[CustomerFeedbackResponse]],
    summary="List feedback submitted within the current tenant",
)
async def list_feedback(
    status_value: FeedbackStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=250),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_ROLES, resource_type="customer-feedback")
    ),
) -> APIResponse[list[CustomerFeedbackResponse]]:
    service = _service(db, current_user)
    items = await service.list_tenant_feedback(status_value=status_value, limit=limit)
    return APIResponse(
        success=True,
        message="Customer feedback retrieved successfully.",
        data=[
            CustomerFeedbackResponse.model_validate(service.serialize_feedback(item))
            for item in items
        ],
    )


@router.get(
    "/summary",
    response_model=APIResponse[CustomerFeedbackSummaryResponse],
    summary="Get feedback status totals for the current tenant",
)
async def tenant_feedback_summary(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_ROLES, resource_type="customer-feedback")
    ),
) -> APIResponse[CustomerFeedbackSummaryResponse]:
    summary = await _service(db, current_user).summary(
        tenant_id=UUID(current_user["tenant_id"])
    )
    return APIResponse(
        success=True,
        message="Feedback summary retrieved successfully.",
        data=CustomerFeedbackSummaryResponse(**summary),
    )


@router.get(
    "/roadmap",
    response_model=APIResponse[list[ProductRoadmapItemResponse]],
    summary="List public product roadmap items",
)
async def list_public_roadmap(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_ROLES, resource_type="product-roadmap")
    ),
) -> APIResponse[list[ProductRoadmapItemResponse]]:
    items = await _service(db, current_user).list_roadmap_items(product_team=False)
    return APIResponse(
        success=True,
        message="Public product roadmap retrieved successfully.",
        data=[ProductRoadmapItemResponse.model_validate(item) for item in items],
    )


@router.get(
    "/product/summary",
    response_model=APIResponse[CustomerFeedbackSummaryResponse],
    summary="Summarize customer feedback across tenants",
)
async def product_feedback_summary(
    tenant_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(_require_product_manager),
) -> APIResponse[CustomerFeedbackSummaryResponse]:
    summary = await _service(db, current_user).summary(tenant_id=tenant_id)
    return APIResponse(
        success=True,
        message="Product feedback summary retrieved successfully.",
        data=CustomerFeedbackSummaryResponse(**summary),
    )


@router.get(
    "/product",
    response_model=APIResponse[list[CustomerFeedbackResponse]],
    summary="List and filter customer feedback across tenants",
)
async def list_product_feedback(
    tenant_id: UUID | None = Query(default=None),
    status_value: FeedbackStatus | None = Query(default=None, alias="status"),
    category: FeedbackCategory | None = Query(default=None),
    priority: FeedbackPriority | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(_require_product_manager),
) -> APIResponse[list[CustomerFeedbackResponse]]:
    service = _service(db, current_user)
    items = await service.list_product_feedback(
        tenant_id=tenant_id,
        status_value=status_value,
        category=category,
        priority=priority,
        limit=limit,
    )
    return APIResponse(
        success=True,
        message="Product feedback retrieved successfully.",
        data=[
            CustomerFeedbackResponse.model_validate(
                service.serialize_feedback(item, product_team=True)
            )
            for item in items
        ],
    )


@router.get(
    "/product/roadmap",
    response_model=APIResponse[list[ProductRoadmapItemResponse]],
    summary="List public and internal roadmap items for the product team",
)
async def list_product_roadmap(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(_require_product_manager),
) -> APIResponse[list[ProductRoadmapItemResponse]]:
    items = await _service(db, current_user).list_roadmap_items(product_team=True)
    return APIResponse(
        success=True,
        message="Product roadmap retrieved successfully.",
        data=[ProductRoadmapItemResponse.model_validate(item) for item in items],
    )


@router.post(
    "/product/roadmap",
    response_model=APIResponse[ProductRoadmapItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a product roadmap item",
)
async def create_product_roadmap_item(
    payload: ProductRoadmapItemCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(_require_product_manager),
) -> APIResponse[ProductRoadmapItemResponse]:
    item = await _service(db, current_user).create_roadmap_item(
        payload, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Product roadmap item created successfully.",
        data=ProductRoadmapItemResponse.model_validate(item),
    )


@router.patch(
    "/product/roadmap/{roadmap_item_id}",
    response_model=APIResponse[ProductRoadmapItemResponse],
    summary="Update roadmap status, visibility or target release",
)
async def update_product_roadmap_item(
    roadmap_item_id: UUID,
    payload: ProductRoadmapItemUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(_require_product_manager),
) -> APIResponse[ProductRoadmapItemResponse]:
    item = await _service(db, current_user).update_roadmap_item(
        roadmap_item_id, payload
    )
    return APIResponse(
        success=True,
        message="Product roadmap item updated successfully.",
        data=ProductRoadmapItemResponse.model_validate(item),
    )


@router.patch(
    "/product/{feedback_id}",
    response_model=APIResponse[CustomerFeedbackResponse],
    summary="Prioritize, triage and link feedback to the product roadmap",
)
async def update_product_feedback(
    feedback_id: UUID,
    payload: CustomerFeedbackUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(_require_product_manager),
) -> APIResponse[CustomerFeedbackResponse]:
    service = _service(db, current_user)
    feedback = await service.update_feedback(
        feedback_id,
        payload,
        actor_id=_actor_id(current_user),
        product_team=True,
    )
    return APIResponse(
        success=True,
        message="Customer feedback updated successfully.",
        data=CustomerFeedbackResponse.model_validate(
            service.serialize_feedback(feedback, product_team=True)
        ),
    )


@router.get(
    "/product/{feedback_id}/history",
    response_model=APIResponse[list[CustomerFeedbackHistoryResponse]],
    summary="Read feedback history across tenants",
)
async def product_feedback_history(
    feedback_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(_require_product_manager),
) -> APIResponse[list[CustomerFeedbackHistoryResponse]]:
    events = await _service(db, current_user).list_history(
        feedback_id, product_team=True
    )
    return APIResponse(
        success=True,
        message="Feedback history retrieved successfully.",
        data=[CustomerFeedbackHistoryResponse.model_validate(item) for item in events],
    )


@router.get(
    "/{feedback_id}",
    response_model=APIResponse[CustomerFeedbackResponse],
    summary="Get one feedback item owned by the current tenant",
)
async def get_feedback(
    feedback_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_ROLES, resource_type="customer-feedback")
    ),
) -> APIResponse[CustomerFeedbackResponse]:
    service = _service(db, current_user)
    item = await service.get_feedback(feedback_id)
    return APIResponse(
        success=True,
        message="Customer feedback retrieved successfully.",
        data=CustomerFeedbackResponse.model_validate(service.serialize_feedback(item)),
    )


@router.get(
    "/{feedback_id}/history",
    response_model=APIResponse[list[CustomerFeedbackHistoryResponse]],
    summary="Read the feedback timeline for the current tenant",
)
async def feedback_history(
    feedback_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_ROLES, resource_type="customer-feedback")
    ),
) -> APIResponse[list[CustomerFeedbackHistoryResponse]]:
    events = await _service(db, current_user).list_history(feedback_id)
    return APIResponse(
        success=True,
        message="Feedback history retrieved successfully.",
        data=[CustomerFeedbackHistoryResponse.model_validate(item) for item in events],
    )
