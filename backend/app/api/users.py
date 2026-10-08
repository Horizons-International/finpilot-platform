from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    get_organization_user_service,
)
from app.core.responses import APIResponse
from app.core.security import require_organization_admin, require_roles
from app.schemas.user import (
    UserCreate,
    UserInvitationCreate,
    UserInvitationResponse,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.organization_user_service import (
    OrganizationUserService,
)
from app.services.user_service import UserService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Creates a new user account.",
)
def create_user(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="user",
        )
    ),
):
    service = UserService(db)

    user = service.create_user(
        user_data,
        actor_tenant_id=UUID(
            current_user["tenant_id"],
        ),
        actor_is_platform_admin=bool(
            current_user["is_platform_admin"],
        ),
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="User created successfully.",
        data=UserResponse.model_validate(user),
    )


@router.get(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Get organization user",
)
def get_user(
    user_id: UUID,
    service: OrganizationUserService = Depends(
        get_organization_user_service,
    ),
    _: dict[str, Any] = Depends(
        require_organization_admin(
            resource_type="user",
        )
    ),
) -> APIResponse[UserResponse]:
    user = service.get_user(
        user_id,
    )

    return APIResponse(
        success=True,
        message="User retrieved successfully.",
        data=UserResponse.model_validate(user),
    )


@router.get(
    "",
    response_model=APIResponse[UserListResponse],
    status_code=status.HTTP_200_OK,
    summary="Get organization users",
    description="Retrieves users belonging to the current organization.",
)
def get_users(
    page: int = 1,
    page_size: int = 20,
    service: OrganizationUserService = Depends(
        get_organization_user_service,
    ),
    _: dict[str, Any] = Depends(
        require_organization_admin(
            resource_type="user",
        )
    ),
) -> APIResponse[UserListResponse]:
    user_list = service.list_users(
        page=page,
        page_size=page_size,
    )

    return APIResponse(
        success=True,
        message="Organization users retrieved successfully.",
        data=user_list,
    )


@router.put(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Update organization user",
)
def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_organization_admin(
            resource_type="user",
        )
    ),
    service: OrganizationUserService = Depends(
        get_organization_user_service,
    ),
) -> APIResponse[UserResponse]:
    user = service.update_user(
        user_id=user_id,
        data=user_data,
        acting_user_id=UUID(current_user["sub"]),
        acting_user_email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="User updated successfully.",
        data=UserResponse.model_validate(user),
    )


@router.patch(
    "/{user_id}/status",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Update organization user status",
)
def update_user_status(
    user_id: UUID,
    status_data: UserStatusUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_organization_admin(
            resource_type="user",
        )
    ),
    service: OrganizationUserService = Depends(
        get_organization_user_service,
    ),
) -> APIResponse[UserResponse]:
    user = service.update_status(
        user_id=user_id,
        data=status_data,
        acting_user_id=UUID(current_user["sub"]),
        acting_user_email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="User status updated successfully.",
        data=UserResponse.model_validate(user),
    )


@router.delete(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Remove organization user",
)
def delete_user(
    user_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_organization_admin(
            resource_type="user",
        )
    ),
    service: OrganizationUserService = Depends(
        get_organization_user_service,
    ),
) -> APIResponse[UserResponse]:
    user = service.delete_user(
        user_id=user_id,
        acting_user_id=UUID(current_user["sub"]),
        acting_user_email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="User removed successfully.",
        data=UserResponse.model_validate(user),
    )


@router.post(
    "/invitations",
    response_model=APIResponse[UserInvitationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Invite organization user",
    description="Invites a new employee to the organization.",
)
def invite_user(
    payload: UserInvitationCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_organization_admin(
            resource_type="user_invitation",
        )
    ),
    service: OrganizationUserService = Depends(
        get_organization_user_service,
    ),
) -> APIResponse[UserInvitationResponse]:
    invitation, token = service.invite_user(
        data=payload,
        invited_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="User invitation created successfully.",
        data=UserInvitationResponse(
            id=invitation.id,
            email=invitation.email,
            first_name=invitation.first_name,
            last_name=invitation.last_name,
            role=UserRole(invitation.role),
            department=invitation.department,
            invitation_token=token,
            expires_at=invitation.expires_at,
        ),
    )
