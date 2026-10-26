"""Sales demo API; gated by SANDBOX_ENABLED and isolated sandbox API keys."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.sandbox_security import (
    SandboxPrincipal,
    require_sandbox_enabled,
    require_sandbox_permission,
)
from app.core.security import require_roles
from app.schemas.sales_demo import (
    SalesDemoAccountCreateResponse,
    SalesDemoCatalogScenario,
    SalesDemoDashboardResponse,
    SalesDemoRecordResponse,
    SalesDemoRecordType,
    SalesDemoVerificationResponse,
)
from app.schemas.sandbox import (
    SandboxAccountCreate,
    SandboxAccountResponse,
    SandboxCustomerResponse,
    SandboxOrganizationResponse,
    SandboxUserResponse,
)
from app.services.sales_demo_service import SalesDemoService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/sandbox/demo",
    tags=["Sales Demo"],
    dependencies=[Depends(require_sandbox_enabled)],
)


@router.post(
    "/accounts",
    response_model=APIResponse[SalesDemoAccountCreateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a sales demo account with seeded synthetic scenarios",
    description=(
        "Only a designated Sales Demo Manager can create an account. "
        "The test key is shown once."
    ),
)
def create_sales_demo_account(
    payload: SandboxAccountCreate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(UserRole.SALES_DEMO_MANAGER, resource_type="sales-demo-account")
    ),
) -> APIResponse[SalesDemoAccountCreateResponse]:
    created = SalesDemoService(db).create_account(payload)
    data = SalesDemoAccountCreateResponse(
        account=SandboxAccountResponse.model_validate(created["account"]),
        organization=SandboxOrganizationResponse.model_validate(
            created["organization"]
        ),
        developer=SandboxUserResponse.model_validate(created["developer"]),
        api_key=created["api_key"],
        sample_customers=[
            SandboxCustomerResponse.model_validate(customer)
            for customer in created["sample_customers"]
        ],
        scenario_count=len(created["scenario_keys"]),
        scenario_keys=created["scenario_keys"],
    )
    return APIResponse(
        success=True,
        message=(
            "Sales demo account created with synthetic data. "
            "The test API key is shown only once."
        ),
        data=data,
    )


@router.get(
    "/dashboard",
    response_model=APIResponse[SalesDemoDashboardResponse],
    summary="Get counts and usage snapshots for this sales demo account",
)
def get_sales_demo_dashboard(
    db: Session = Depends(get_db),
    principal: SandboxPrincipal = Depends(require_sandbox_permission("sandbox:read")),
) -> APIResponse[SalesDemoDashboardResponse]:
    dashboard = SalesDemoService(db).get_dashboard(principal.account_id)
    return APIResponse(
        success=True,
        message="Sales demo dashboard retrieved successfully.",
        data=SalesDemoDashboardResponse(**dashboard),
    )


@router.get(
    "/scenarios",
    response_model=APIResponse[list[SalesDemoCatalogScenario]],
    summary="List the guided sales demo scenarios",
)
def list_sales_demo_scenarios(
    db: Session = Depends(get_db),
    principal: SandboxPrincipal = Depends(require_sandbox_permission("sandbox:read")),
) -> APIResponse[list[SalesDemoCatalogScenario]]:
    scenarios = SalesDemoService(db).list_catalog()
    return APIResponse(
        success=True,
        message="Sales demo scenarios retrieved successfully.",
        data=[SalesDemoCatalogScenario(**item) for item in scenarios],
    )


@router.get(
    "/verifications",
    response_model=APIResponse[list[SalesDemoVerificationResponse]],
    summary="List seeded verification outcomes for this demo account",
)
def list_sales_demo_verifications(
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
    principal: SandboxPrincipal = Depends(require_sandbox_permission("sandbox:read")),
) -> APIResponse[list[SalesDemoVerificationResponse]]:
    verifications = SalesDemoService(db).list_verifications(
        principal.account_id, limit=limit
    )
    return APIResponse(
        success=True,
        message="Sales demo verification examples retrieved successfully.",
        data=[SalesDemoVerificationResponse(**item) for item in verifications],
    )


@router.get(
    "/records",
    response_model=APIResponse[list[SalesDemoRecordResponse]],
    summary="List demo records, optionally filtered by record type",
)
def list_sales_demo_records(
    record_type: SalesDemoRecordType | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
    principal: SandboxPrincipal = Depends(require_sandbox_permission("sandbox:read")),
) -> APIResponse[list[SalesDemoRecordResponse]]:
    records = SalesDemoService(db).list_records(
        principal.account_id,
        record_type=record_type,
        limit=limit,
    )
    return APIResponse(
        success=True,
        message="Sales demo records retrieved successfully.",
        data=[SalesDemoRecordResponse(**item) for item in records],
    )


@router.post(
    "/reset",
    response_model=APIResponse[SalesDemoDashboardResponse],
    summary="Reset demo customers, verification examples and scenario records",
    description=(
        "Requires sandbox:admin. Preserves account, users, API keys and webhook "
        "subscriptions; deletes only records for the authenticated demo account."
    ),
)
def reset_sales_demo_data(
    db: Session = Depends(get_db),
    principal: SandboxPrincipal = Depends(require_sandbox_permission("sandbox:admin")),
) -> APIResponse[SalesDemoDashboardResponse]:
    dashboard = SalesDemoService(db).reset_demo_data(principal.account_id)
    return APIResponse(
        success=True,
        message=(
            "Demo data reset successfully. The account and its access keys "
            "were preserved."
        ),
        data=SalesDemoDashboardResponse(**dashboard),
    )
