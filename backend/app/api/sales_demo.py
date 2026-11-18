"""Async sales-demo API, gated by SANDBOX_ENABLED and sandbox API-key scopes."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_sandbox_security import (
    AsyncSandboxPrincipal,
    require_async_sandbox_permission,
    require_sandbox_enabled,
)
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
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
from app.services.async_sales_demo_service import AsyncSalesDemoService
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
async def create_sales_demo_account(
    payload: SandboxAccountCreate,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.SALES_DEMO_MANAGER, resource_type="sales-demo-account"
        )
    ),
) -> APIResponse[SalesDemoAccountCreateResponse]:
    created = await AsyncSalesDemoService(db).create_account(payload)
    data = SalesDemoAccountCreateResponse(
        account=SandboxAccountResponse.model_validate(created["account"]),
        organization=SandboxOrganizationResponse.model_validate(
            created["organization"]
        ),
        developer=SandboxUserResponse.model_validate(created["developer"]),
        api_key=created["api_key"],
        sample_customers=[
            SandboxCustomerResponse.model_validate(item)
            for item in created["sample_customers"]
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


@router.get("/dashboard", response_model=APIResponse[SalesDemoDashboardResponse])
async def get_sales_demo_dashboard(
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[SalesDemoDashboardResponse]:
    dashboard = await AsyncSalesDemoService(db).get_dashboard(principal.account_id)
    return APIResponse(
        success=True,
        message="Sales demo dashboard retrieved successfully.",
        data=SalesDemoDashboardResponse(**dashboard),
    )


@router.get("/scenarios", response_model=APIResponse[list[SalesDemoCatalogScenario]])
async def list_sales_demo_scenarios(
    _: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[list[SalesDemoCatalogScenario]]:
    scenarios = AsyncSalesDemoService.list_catalog()
    return APIResponse(
        success=True,
        message="Sales demo scenarios retrieved successfully.",
        data=[SalesDemoCatalogScenario(**item) for item in scenarios],
    )


@router.get(
    "/verifications",
    response_model=APIResponse[list[SalesDemoVerificationResponse]],
)
async def list_sales_demo_verifications(
    limit: int = Query(default=100, ge=1, le=250),
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[list[SalesDemoVerificationResponse]]:
    verifications = await AsyncSalesDemoService(db).list_verifications(
        principal.account_id, limit=limit
    )
    return APIResponse(
        success=True,
        message="Sales demo verification examples retrieved successfully.",
        data=[SalesDemoVerificationResponse(**item) for item in verifications],
    )


@router.get("/records", response_model=APIResponse[list[SalesDemoRecordResponse]])
async def list_sales_demo_records(
    record_type: SalesDemoRecordType | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=250),
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[list[SalesDemoRecordResponse]]:
    records = await AsyncSalesDemoService(db).list_records(
        principal.account_id, record_type=record_type, limit=limit
    )
    return APIResponse(
        success=True,
        message="Sales demo records retrieved successfully.",
        data=[SalesDemoRecordResponse(**item) for item in records],
    )


@router.post("/reset", response_model=APIResponse[SalesDemoDashboardResponse])
async def reset_sales_demo_data(
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:admin")
    ),
) -> APIResponse[SalesDemoDashboardResponse]:
    dashboard = await AsyncSalesDemoService(db).reset_demo_data(principal.account_id)
    return APIResponse(
        success=True,
        message=(
            "Demo data reset successfully. The account and its access keys "
            "were preserved."
        ),
        data=SalesDemoDashboardResponse(**dashboard),
    )
