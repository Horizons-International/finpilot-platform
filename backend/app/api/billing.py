"""Platform billing plan management and tenant-scoped invoice endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user, require_platform_admin
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
from app.services.billing_service import BillingService
from app.utils.enums import UserRole
from app.utils.errors import forbidden

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


def _service(db: Session) -> BillingService:
    return BillingService(db)


def _require_invoice_reader(current_user: User) -> None:
    """Protect pricing and invoice details from ordinary tenant users."""
    allowed_roles = {
        UserRole.ADMINISTRATOR.value,
        UserRole.ORGANIZATION_ADMIN.value,
        UserRole.AUDITOR.value,
    }
    if not current_user.is_platform_admin and current_user.role not in allowed_roles:
        raise forbidden("Only tenant administrators or auditors can view invoices.")


@router.get(
    "/plans",
    response_model=APIResponse[list[BillingPlanResponse]],
    summary="List commercial billing plans",
)
def list_billing_plans(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[list[BillingPlanResponse]]:
    plans = _service(db).list_plans(include_inactive=include_inactive)
    return APIResponse(
        success=True,
        message="Billing plans retrieved successfully.",
        data=[BillingPlanResponse.model_validate(item) for item in plans],
    )


@router.post(
    "/plans",
    response_model=APIResponse[BillingPlanResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a commercial billing plan",
)
def create_billing_plan(
    payload: BillingPlanCreate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[BillingPlanResponse]:
    plan = _service(db).create_plan(payload)
    return APIResponse(
        success=True,
        message="Billing plan created successfully.",
        data=BillingPlanResponse.model_validate(plan),
    )


@router.get(
    "/plans/{plan_id}",
    response_model=APIResponse[BillingPlanResponse],
    summary="Get a billing plan",
)
def get_billing_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[BillingPlanResponse]:
    plan = _service(db).get_plan(plan_id)
    return APIResponse(
        success=True,
        message="Billing plan retrieved successfully.",
        data=BillingPlanResponse.model_validate(plan),
    )


@router.patch(
    "/plans/{plan_id}",
    response_model=APIResponse[BillingPlanResponse],
    summary="Update plan terms or activate/deactivate a plan",
)
def update_billing_plan(
    plan_id: UUID,
    payload: BillingPlanUpdate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[BillingPlanResponse]:
    plan = _service(db).update_plan(plan_id, payload)
    return APIResponse(
        success=True,
        message="Billing plan updated successfully.",
        data=BillingPlanResponse.model_validate(plan),
    )


@router.post(
    "/assignments",
    response_model=APIResponse[BillingPlanAssignmentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Assign a billing plan to a customer tenant",
)
def assign_billing_plan(
    payload: BillingPlanAssignmentCreate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[BillingPlanAssignmentResponse]:
    assignment = _service(db).assign_plan(payload)
    return APIResponse(
        success=True,
        message="Billing plan assigned successfully.",
        data=BillingPlanAssignmentResponse.model_validate(assignment),
    )


@router.get(
    "/assignments/{tenant_id}",
    response_model=APIResponse[BillingPlanAssignmentResponse],
    summary="Get the current billing plan assignment for a customer tenant",
)
def get_billing_assignment(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[BillingPlanAssignmentResponse]:
    assignment = _service(db).get_assignment(tenant_id)
    return APIResponse(
        success=True,
        message="Billing plan assignment retrieved successfully.",
        data=BillingPlanAssignmentResponse.model_validate(assignment),
    )


@router.post(
    "/invoices/generate",
    response_model=APIResponse[InvoiceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Calculate usage charges and generate an invoice snapshot",
)
def generate_invoice(
    payload: InvoiceGenerateRequest,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[InvoiceResponse]:
    invoice = _service(db).generate_invoice(payload)
    return APIResponse(
        success=True,
        message="Invoice generated successfully.",
        data=InvoiceResponse.model_validate(_service(db).serialize_invoice(invoice)),
    )


@router.get(
    "/invoices",
    response_model=APIResponse[list[InvoiceResponse]],
    summary="List invoices visible to the current tenant",
)
def list_invoices(
    tenant_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[InvoiceResponse]]:
    _require_invoice_reader(current_user)
    target_tenant_id = tenant_id or current_user.tenant_id
    if (
        not current_user.is_platform_admin
        and target_tenant_id != current_user.tenant_id
    ):
        raise forbidden("You cannot view invoices belonging to another tenant.")
    invoices = _service(db).list_invoices(target_tenant_id, limit=limit)
    return APIResponse(
        success=True,
        message="Invoices retrieved successfully.",
        data=[InvoiceResponse.model_validate(item) for item in invoices],
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=APIResponse[InvoiceResponse],
    summary="Get an invoice visible to the current tenant",
)
def get_invoice(
    invoice_id: UUID,
    tenant_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[InvoiceResponse]:
    _require_invoice_reader(current_user)
    target_tenant_id = tenant_id or current_user.tenant_id
    if (
        not current_user.is_platform_admin
        and target_tenant_id != current_user.tenant_id
    ):
        raise forbidden("You cannot view invoices belonging to another tenant.")
    invoice = _service(db).get_invoice(invoice_id, target_tenant_id)
    return APIResponse(
        success=True,
        message="Invoice retrieved successfully.",
        data=InvoiceResponse.model_validate(invoice),
    )


@router.patch(
    "/invoices/{invoice_id}/status",
    response_model=APIResponse[InvoiceResponse],
    summary="Issue, mark paid, or void an invoice",
)
def update_invoice_status(
    invoice_id: UUID,
    payload: InvoiceStatusUpdate,
    tenant_id: UUID = Query(...),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[InvoiceResponse]:
    invoice = _service(db).update_invoice_status(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        next_status=payload.status,
    )
    return APIResponse(
        success=True,
        message="Invoice status updated successfully.",
        data=InvoiceResponse.model_validate(invoice),
    )
