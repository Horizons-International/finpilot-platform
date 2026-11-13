"""Native-async billing plan management and tenant-scoped invoice endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import get_async_current_user, require_async_platform_admin
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.models.user import User
from app.schemas.billing import (
    BillingPlanAssignmentCreate,
    BillingPlanAssignmentResponse,
    BillingPlanCreate,
    BillingPlanResponse,
    BillingPlanUpdate,
    InvoiceGenerateRequest,
    InvoiceResponse,
    InvoiceStatusUpdate,
)
from app.services.async_billing_service import AsyncBillingService
from app.utils.enums import UserRole
from app.utils.errors import forbidden

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


def _require_invoice_reader(user: User) -> None:
    allowed = {
        UserRole.ADMINISTRATOR.value,
        UserRole.ORGANIZATION_ADMIN.value,
        UserRole.AUDITOR.value,
    }
    role_value = getattr(user.role, "value", user.role)
    if not user.is_platform_admin and role_value not in allowed:
        raise forbidden("Only tenant administrators or auditors can view invoices.")


@router.get("/plans", response_model=APIResponse[list[BillingPlanResponse]])
async def list_billing_plans(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[list[BillingPlanResponse]]:
    rows = await AsyncBillingService(db).list_plans(include_inactive=include_inactive)
    return APIResponse(
        success=True,
        message="Billing plans retrieved successfully.",
        data=[BillingPlanResponse.model_validate(row) for row in rows],
    )


@router.post(
    "/plans",
    response_model=APIResponse[BillingPlanResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_billing_plan(
    payload: BillingPlanCreate,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[BillingPlanResponse]:
    row = await AsyncBillingService(db).create_plan(payload)
    return APIResponse(
        success=True,
        message="Billing plan created successfully.",
        data=BillingPlanResponse.model_validate(row),
    )


@router.get("/plans/{plan_id}", response_model=APIResponse[BillingPlanResponse])
async def get_billing_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[BillingPlanResponse]:
    row = await AsyncBillingService(db).get_plan(plan_id)
    return APIResponse(
        success=True,
        message="Billing plan retrieved successfully.",
        data=BillingPlanResponse.model_validate(row),
    )


@router.patch("/plans/{plan_id}", response_model=APIResponse[BillingPlanResponse])
async def update_billing_plan(
    plan_id: UUID,
    payload: BillingPlanUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[BillingPlanResponse]:
    row = await AsyncBillingService(db).update_plan(plan_id, payload)
    return APIResponse(
        success=True,
        message="Billing plan updated successfully.",
        data=BillingPlanResponse.model_validate(row),
    )


@router.post(
    "/assignments",
    response_model=APIResponse[BillingPlanAssignmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def assign_billing_plan(
    payload: BillingPlanAssignmentCreate,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[BillingPlanAssignmentResponse]:
    data = await AsyncBillingService(db).assign_plan(payload)
    return APIResponse(
        success=True,
        message="Billing plan assigned successfully.",
        data=BillingPlanAssignmentResponse.model_validate(data),
    )


@router.get(
    "/assignments/{tenant_id}",
    response_model=APIResponse[BillingPlanAssignmentResponse],
)
async def get_billing_assignment(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[BillingPlanAssignmentResponse]:
    data = await AsyncBillingService(db).get_assignment(tenant_id)
    return APIResponse(
        success=True,
        message="Billing plan assignment retrieved successfully.",
        data=BillingPlanAssignmentResponse.model_validate(data),
    )


@router.post(
    "/invoices/generate",
    response_model=APIResponse[InvoiceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_invoice(
    payload: InvoiceGenerateRequest,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[InvoiceResponse]:
    service = AsyncBillingService(db)
    invoice = await service.generate_invoice(payload)
    return APIResponse(
        success=True,
        message="Invoice generated successfully.",
        data=InvoiceResponse.model_validate(service.serialize_invoice(invoice)),
    )


@router.get("/invoices", response_model=APIResponse[list[InvoiceResponse]])
async def list_invoices(
    tenant_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[list[InvoiceResponse]]:
    _require_invoice_reader(current_user)
    target = tenant_id or current_user.tenant_id
    if not current_user.is_platform_admin and target != current_user.tenant_id:
        raise forbidden("You cannot view invoices belonging to another tenant.")
    rows = await AsyncBillingService(db).list_invoices(target, limit=limit)
    return APIResponse(
        success=True,
        message="Invoices retrieved successfully.",
        data=[InvoiceResponse.model_validate(row) for row in rows],
    )


@router.get("/invoices/{invoice_id}", response_model=APIResponse[InvoiceResponse])
async def get_invoice(
    invoice_id: UUID,
    tenant_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[InvoiceResponse]:
    _require_invoice_reader(current_user)
    target = tenant_id or current_user.tenant_id
    if not current_user.is_platform_admin and target != current_user.tenant_id:
        raise forbidden("You cannot view invoices belonging to another tenant.")
    row = await AsyncBillingService(db).get_invoice(invoice_id, target)
    return APIResponse(
        success=True,
        message="Invoice retrieved successfully.",
        data=InvoiceResponse.model_validate(row),
    )


@router.patch(
    "/invoices/{invoice_id}/status", response_model=APIResponse[InvoiceResponse]
)
async def update_invoice_status(
    invoice_id: UUID,
    payload: InvoiceStatusUpdate,
    tenant_id: UUID = Query(...),
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[InvoiceResponse]:
    row = await AsyncBillingService(db).update_invoice_status(
        invoice_id=invoice_id, tenant_id=tenant_id, next_status=payload.status
    )
    return APIResponse(
        success=True,
        message="Invoice status updated successfully.",
        data=InvoiceResponse.model_validate(row),
    )
