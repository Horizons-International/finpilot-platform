"""Native-async organization user administration and invitation endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.user import (
    UserCreate,
    UserInvitationCreate,
    UserInvitationResponse,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.async_organization_user_service import AsyncOrganizationUserService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


def _meta(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncOrganizationUserService:
    return AsyncOrganizationUserService(db, UUID(user["tenant_id"]))


@router.post(
    "",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
)
async def create_user(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="user")
    ),
) -> APIResponse[UserResponse]:
    ip, agent = _meta(request)
    target = user_data.tenant_id or UUID(current_user["tenant_id"])
    item = await _service(db, current_user).create_user(
        user_data,
        actor_id=UUID(current_user["sub"]),
        actor_email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
        target_tenant_id=target,
        actor_is_platform_admin=bool(current_user.get("is_platform_admin")),
    )
    return APIResponse(
        success=True,
        message="User created successfully.",
        data=UserResponse.model_validate(item),
    )


@router.get(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN, resource_type="user"
        )
    ),
) -> APIResponse[UserResponse]:
    item = await _service(db, current_user).get_user(user_id)
    return APIResponse(
        success=True,
        message="User retrieved successfully.",
        data=UserResponse.model_validate(item),
    )


@router.get(
    "", response_model=APIResponse[UserListResponse], status_code=status.HTTP_200_OK
)
async def get_users(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN, resource_type="user"
        )
    ),
) -> APIResponse[UserListResponse]:
    data = await _service(db, current_user).list_users(page=page, page_size=page_size)
    return APIResponse(
        success=True, message="Organization users retrieved successfully.", data=data
    )


@router.put(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN, resource_type="user"
        )
    ),
) -> APIResponse[UserResponse]:
    ip, agent = _meta(request)
    item = await _service(db, current_user).update_user(
        user_id=user_id,
        data=user_data,
        actor_id=UUID(current_user["sub"]),
        actor_email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="User updated successfully.",
        data=UserResponse.model_validate(item),
    )


@router.patch(
    "/{user_id}/status",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
)
async def update_user_status(
    user_id: UUID,
    status_data: UserStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN, resource_type="user"
        )
    ),
) -> APIResponse[UserResponse]:
    ip, agent = _meta(request)
    item = await _service(db, current_user).update_status(
        user_id=user_id,
        data=status_data,
        actor_id=UUID(current_user["sub"]),
        actor_email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="User status updated successfully.",
        data=UserResponse.model_validate(item),
    )


@router.delete(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
)
async def delete_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN, resource_type="user"
        )
    ),
) -> APIResponse[UserResponse]:
    ip, agent = _meta(request)
    item = await _service(db, current_user).delete_user(
        user_id=user_id,
        actor_id=UUID(current_user["sub"]),
        actor_email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="User removed successfully.",
        data=UserResponse.model_validate(item),
    )


@router.post(
    "/invitations",
    response_model=APIResponse[UserInvitationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def invite_user(
    payload: UserInvitationCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.ORGANIZATION_ADMIN,
            resource_type="user_invitation",
        )
    ),
) -> APIResponse[UserInvitationResponse]:
    ip, agent = _meta(request)
    invitation, token = await _service(db, current_user).invite_user(
        data=payload,
        invited_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    data = UserInvitationResponse(
        id=invitation.id,
        email=invitation.email,
        first_name=invitation.first_name,
        last_name=invitation.last_name,
        role=UserRole(invitation.role),
        department=invitation.department,
        invitation_token=token,
        expires_at=invitation.expires_at,
    )
    return APIResponse(
        success=True, message="User invitation created successfully.", data=data
    )
