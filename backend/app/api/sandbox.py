"""Native-async sandbox API. No route in this module calls production services."""

from typing import Any
from uuid import UUID

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
from app.schemas.sandbox import (
    SandboxAccountCreate,
    SandboxAccountCreatedResponse,
    SandboxAccountResponse,
    SandboxAPIKeyCreate,
    SandboxAPIKeyCreatedResponse,
    SandboxAPIKeyResponse,
    SandboxCustomerCreate,
    SandboxCustomerResponse,
    SandboxOrganizationResponse,
    SandboxUserCreate,
    SandboxUserResponse,
    SandboxVerificationCreate,
    SandboxVerificationResponse,
    SandboxWebhookCreate,
    SandboxWebhookEventResponse,
    SandboxWebhookResponse,
    SandboxWebhookSimulationRequest,
)
from app.services.async_sandbox_service import AsyncSandboxService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/sandbox",
    tags=["Sandbox"],
    dependencies=[Depends(require_sandbox_enabled)],
)


@router.post(
    "/accounts",
    response_model=APIResponse[SandboxAccountCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create an isolated sandbox account",
)
async def create_sandbox_account(
    payload: SandboxAccountCreate,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.SALES_DEMO_MANAGER, resource_type="sandbox-account"
        )
    ),
) -> APIResponse[SandboxAccountCreatedResponse]:
    created = await AsyncSandboxService(db).create_account(payload)
    response = SandboxAccountCreatedResponse(
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
    )
    return APIResponse(
        success=True,
        message=(
            "Sandbox account created. Copy the test API key now; it is shown only once."
        ),
        data=response,
    )


@router.get("/account", response_model=APIResponse[SandboxAccountResponse])
async def get_sandbox_account(
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[SandboxAccountResponse]:
    account = await AsyncSandboxService(db).get_account(principal.account_id)
    return APIResponse(
        success=True,
        message="Sandbox account retrieved successfully.",
        data=SandboxAccountResponse.model_validate(account),
    )


@router.get("/users", response_model=APIResponse[list[SandboxUserResponse]])
async def list_sandbox_users(
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[list[SandboxUserResponse]]:
    users = await AsyncSandboxService(db).list_users(principal.account_id)
    return APIResponse(
        success=True,
        message="Sandbox users retrieved successfully.",
        data=[SandboxUserResponse.model_validate(item) for item in users],
    )


@router.post(
    "/users",
    response_model=APIResponse[SandboxUserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_sandbox_user(
    payload: SandboxUserCreate,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:write")
    ),
) -> APIResponse[SandboxUserResponse]:
    user = await AsyncSandboxService(db).create_user(principal.account_id, payload)
    return APIResponse(
        success=True,
        message="Synthetic sandbox user created.",
        data=SandboxUserResponse.model_validate(user),
    )


@router.get(
    "/account/api-keys",
    response_model=APIResponse[list[SandboxAPIKeyResponse]],
)
async def list_sandbox_api_keys(
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:admin")
    ),
) -> APIResponse[list[SandboxAPIKeyResponse]]:
    keys = await AsyncSandboxService(db).list_api_keys(principal.account_id)
    return APIResponse(
        success=True,
        message="Sandbox API keys retrieved successfully.",
        data=[SandboxAPIKeyResponse.model_validate(item) for item in keys],
    )


@router.post(
    "/account/api-keys",
    response_model=APIResponse[SandboxAPIKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_sandbox_api_key(
    payload: SandboxAPIKeyCreate,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:admin")
    ),
) -> APIResponse[SandboxAPIKeyCreatedResponse]:
    key, raw_key = await AsyncSandboxService(db).create_api_key(
        principal.account_id, payload
    )
    return APIResponse(
        success=True,
        message=(
            "Sandbox API key created. Copy the secret now; "
            "it cannot be retrieved later."
        ),
        data=SandboxAPIKeyCreatedResponse(
            key=SandboxAPIKeyResponse.model_validate(key), api_key=raw_key
        ),
    )


@router.post(
    "/account/api-keys/{key_id}/revoke",
    response_model=APIResponse[SandboxAPIKeyResponse],
)
async def revoke_sandbox_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:admin")
    ),
) -> APIResponse[SandboxAPIKeyResponse]:
    key = await AsyncSandboxService(db).revoke_api_key(principal.account_id, key_id)
    return APIResponse(
        success=True,
        message="Sandbox API key revoked.",
        data=SandboxAPIKeyResponse.model_validate(key),
    )


@router.get("/customers", response_model=APIResponse[list[SandboxCustomerResponse]])
async def list_sandbox_customers(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[list[SandboxCustomerResponse]]:
    customers = await AsyncSandboxService(db).list_customers(
        principal.account_id, limit
    )
    return APIResponse(
        success=True,
        message="Sandbox customers retrieved successfully.",
        data=[SandboxCustomerResponse.model_validate(item) for item in customers],
    )


@router.post(
    "/customers",
    response_model=APIResponse[SandboxCustomerResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_sandbox_customer(
    payload: SandboxCustomerCreate,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:write")
    ),
) -> APIResponse[SandboxCustomerResponse]:
    customer = await AsyncSandboxService(db).create_customer(
        principal.account_id, payload
    )
    return APIResponse(
        success=True,
        message="Synthetic sandbox customer created.",
        data=SandboxCustomerResponse.model_validate(customer),
    )


@router.get(
    "/customers/{customer_id}", response_model=APIResponse[SandboxCustomerResponse]
)
async def get_sandbox_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[SandboxCustomerResponse]:
    customer = await AsyncSandboxService(db).get_customer(
        principal.account_id, customer_id
    )
    return APIResponse(
        success=True,
        message="Sandbox customer retrieved successfully.",
        data=SandboxCustomerResponse.model_validate(customer),
    )


@router.post(
    "/customers/{customer_id}/verifications",
    response_model=APIResponse[SandboxVerificationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def simulate_verification(
    customer_id: UUID,
    payload: SandboxVerificationCreate,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:write")
    ),
) -> APIResponse[SandboxVerificationResponse]:
    result = await AsyncSandboxService(db).create_verification(
        principal.account_id, customer_id, payload
    )
    return APIResponse(
        success=True,
        message=(
            "Sandbox verification simulated; no real verification provider was called."
        ),
        data=SandboxVerificationResponse.model_validate(result),
    )


@router.get(
    "/verifications/{verification_id}",
    response_model=APIResponse[SandboxVerificationResponse],
)
async def get_sandbox_verification(
    verification_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:read")
    ),
) -> APIResponse[SandboxVerificationResponse]:
    result = await AsyncSandboxService(db).get_verification(
        principal.account_id, verification_id
    )
    return APIResponse(
        success=True,
        message="Sandbox verification retrieved successfully.",
        data=SandboxVerificationResponse.model_validate(result),
    )


@router.get("/webhooks", response_model=APIResponse[list[SandboxWebhookResponse]])
async def list_sandbox_webhooks(
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:webhooks")
    ),
) -> APIResponse[list[SandboxWebhookResponse]]:
    rows = await AsyncSandboxService(db).list_webhooks(principal.account_id)
    return APIResponse(
        success=True,
        message="Sandbox webhooks retrieved successfully.",
        data=[SandboxWebhookResponse.model_validate(item) for item in rows],
    )


@router.post(
    "/webhooks",
    response_model=APIResponse[SandboxWebhookResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_sandbox_webhook(
    payload: SandboxWebhookCreate,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:webhooks")
    ),
) -> APIResponse[SandboxWebhookResponse]:
    webhook = await AsyncSandboxService(db).create_webhook(
        principal.account_id, payload
    )
    return APIResponse(
        success=True,
        message=(
            "Sandbox webhook registered. Events are simulated and are not "
            "sent to the endpoint URL."
        ),
        data=SandboxWebhookResponse.model_validate(webhook),
    )


@router.post(
    "/webhooks/{webhook_id}/simulate",
    response_model=APIResponse[SandboxWebhookEventResponse],
    status_code=status.HTTP_201_CREATED,
)
async def simulate_sandbox_webhook(
    webhook_id: UUID,
    payload: SandboxWebhookSimulationRequest,
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:webhooks")
    ),
) -> APIResponse[SandboxWebhookEventResponse]:
    event = await AsyncSandboxService(db).simulate_webhook(
        principal.account_id, webhook_id, payload
    )
    return APIResponse(
        success=True,
        message="Synthetic webhook payload created. No outbound HTTP request was made.",
        data=SandboxWebhookEventResponse.model_validate(event),
    )


@router.get(
    "/webhooks/{webhook_id}/events",
    response_model=APIResponse[list[SandboxWebhookEventResponse]],
)
async def list_sandbox_webhook_events(
    webhook_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    principal: AsyncSandboxPrincipal = Depends(
        require_async_sandbox_permission("sandbox:webhooks")
    ),
) -> APIResponse[list[SandboxWebhookEventResponse]]:
    events = await AsyncSandboxService(db).list_webhook_events(
        principal.account_id, webhook_id, limit
    )
    return APIResponse(
        success=True,
        message="Sandbox webhook events retrieved successfully.",
        data=[SandboxWebhookEventResponse.model_validate(item) for item in events],
    )
